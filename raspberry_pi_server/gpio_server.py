"""
Raspberry Pi GPIO Monitor Server
---------------------------------
Subscribes to MQTT topics published by ESP32 GPIO client devices,
cross-references each device's MAC address against a commissioning
registry (registry.py) to show what equipment it's attached to, and
renders each device as a card on the dashboard using a "device type"
template (device_types.py). Most types use the generic per-GPIO label
grid; special types (like "Talent Pack Decoder", layout
"talent_pack_decoder") use a bespoke card renderer defined below.

The dashboard polls for state in the background via JS (not a full-page
meta-refresh), so inline-editable card fields (e.g. decoder name/frequency/
receiver) aren't interrupted by a periodic reload.

SETUP
-----
1) Install and start an MQTT broker on this Pi:
     sudo apt update
     sudo apt install -y mosquitto mosquitto-clients
     sudo systemctl enable --now mosquitto

2) Install Python dependencies:
     pip install -r requirements.txt

3) Run:
     python3 gpio_server.py

4) Open the dashboard:      http://<pi-ip>:8080
   Commission a new unit:   http://<pi-ip>:8080/commission
   Manage card types:       http://<pi-ip>:8080/device-types
   Raw JSON:                http://<pi-ip>:8080/api/devices
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string, request, redirect, url_for, send_file

import registry
import device_types
import event_log

# ================= CONFIG =================
MQTT_BROKER = "localhost"       # broker running on this same Pi
MQTT_PORT = 1883
MQTT_STATUS_TOPIC = "gpio/+/status"
MQTT_LWT_TOPIC = "gpio/+/lwt"
STALE_TIMEOUT_SEC = 30           # mark a device offline if silent this long
WEB_PORT = 8080
NUM_GPIO_GENERIC = 12            # channel count for the generic card layout
# ============================================

app = Flask(__name__)
devices = {}
devices_lock = threading.Lock()

device_types.ensure_builtin_types()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT broker (rc={rc})")
    client.subscribe(MQTT_STATUS_TOPIC)
    client.subscribe(MQTT_LWT_TOPIC)


def on_message(client, userdata, msg):
    parts = msg.topic.split("/")
    if len(parts) < 3:
        return
    device_id, kind = parts[1], parts[2]   # "status" or "lwt"

    with devices_lock:
        entry = devices.setdefault(device_id, {
            "mac": None,
            "gpio": None,
            "ip": None,
            "status": "unknown",
            "last_seen": None,
            "equipment": None,   # filled in from the registry below
        })

        if kind == "status":
            try:
                payload = json.loads(msg.payload.decode())
                old_gpio = entry.get("gpio")
                new_gpio = payload.get("gpio")
                entry["gpio"] = new_gpio
                entry["ip"] = payload.get("ip")
                entry["mac"] = payload.get("mac")
                entry["last_seen"] = now_iso()
                entry["status"] = "online"
                entry["equipment"] = registry.get_equipment(entry["mac"])
                maybe_log_tpd_changes(device_id, entry["mac"], entry["equipment"], old_gpio, new_gpio)
            except json.JSONDecodeError:
                print(f"Bad payload from {device_id}: {msg.payload!r}")

        elif kind == "lwt":
            entry["status"] = msg.payload.decode()   # "online" / "offline"
            entry["last_seen"] = now_iso()


def stale_checker():
    """Marks a device 'stale' if nothing has arrived in a while.
    Covers abrupt power loss / cable pulls where the LWT message
    may not always make it out before the connection drops."""
    while True:
        time.sleep(5)
        cutoff = time.time() - STALE_TIMEOUT_SEC
        with devices_lock:
            for entry in devices.values():
                if not entry["last_seen"]:
                    continue
                last_seen_ts = datetime.fromisoformat(entry["last_seen"]).timestamp()
                if last_seen_ts < cutoff and entry["status"] == "online":
                    entry["status"] = "stale"


# --- Talent Pack Decoder: fixed 5-channel-per-decoder layout ---
# Channel order within each decoder's 5-channel block:
#   0: On-Air (green)   1: Prod (yellow)
#   2: Error/Manual A   3: Error/Manual B   (2-way LED: A=Error/red, B=Manual/blue)
#   4: Call (red)
TPD_CHANNELS_PER_DECODER = 5
TPD_NUM_DECODERS = 3


def maybe_log_tpd_changes(device_id, mac, equipment, old_gpio, new_gpio):
    """Compares the previous and new GPIO readings for a Talent Pack
    Decoder device and writes a CSV log row for each On-Air/Prod channel
    that changed state, but only for decoders where the user has checked
    "Log this path". No-ops entirely for non-TPD devices, and skips the
    very first reading after startup/reconnect (old_gpio is None) since
    that's not a real transition, just the initial state becoming known.
    """
    if old_gpio is None or not equipment or not equipment.get("device_type"):
        return
    type_def = device_types.get_type(equipment["device_type"])
    if not type_def or type_def.get("layout") != "talent_pack_decoder":
        return

    stored_decoders = equipment.get("decoders", [])
    for i in range(TPD_NUM_DECODERS):
        dec_info = stored_decoders[i] if i < len(stored_decoders) else {}
        if not dec_info.get("log_enabled"):
            continue
        decoder_name = dec_info.get("name") or f"Decoder {i + 1}"
        base = i * TPD_CHANNELS_PER_DECODER
        for offset, channel_name in ((0, "on_air"), (1, "prod")):
            idx = base + offset
            old_val = old_gpio[idx] if idx < len(old_gpio) else None
            new_val = new_gpio[idx] if new_gpio and idx < len(new_gpio) else None
            if old_val is not None and new_val is not None and old_val != new_val:
                event_log.log_event(device_id, mac, decoder_name, channel_name, new_val)


def talent_pack_decoder_view(entry, equipment):
    """Builds the render-ready view for a Talent Pack Decoder card: LED
    states per decoder (from live GPIO values) paired with that decoder's
    live-editable name/frequency/receiver text (from the registry)."""
    gpio_values = entry.get("gpio") or []
    stored_decoders = (equipment or {}).get("decoders", [])

    decoders = []
    for i in range(TPD_NUM_DECODERS):
        base = i * TPD_CHANNELS_PER_DECODER
        chunk = gpio_values[base:base + TPD_CHANNELS_PER_DECODER]
        while len(chunk) < TPD_CHANNELS_PER_DECODER:
            chunk.append(None)
        on_air, prod, err_a, err_b, call = chunk

        if err_a == 1 and err_b != 1:
            err_man_state = "error"
        elif err_b == 1 and err_a != 1:
            err_man_state = "manual"
        elif err_a == 1 and err_b == 1:
            err_man_state = "error"   # both asserted: treat as error (priority)
        else:
            err_man_state = "off"

        text = stored_decoders[i] if i < len(stored_decoders) else {}
        decoders.append({
            "index": i,
            "on_air": on_air,
            "prod": prod,
            "err_man_state": err_man_state,
            "call": call,
            "name": text.get("name", ""),
            "frequency": text.get("frequency", ""),
            "receiver": text.get("receiver", ""),
            "log_enabled": bool(text.get("log_enabled", False)),
        })

    return decoders


def card_view(entry):
    """Builds the render-ready view for one device's card. Branches to a
    bespoke renderer for special layouts (e.g. talent_pack_decoder);
    otherwise falls back to the generic per-GPIO label grid."""
    equipment = entry.get("equipment")
    type_def = None
    if equipment and equipment.get("device_type"):
        type_def = device_types.get_type(equipment["device_type"])

    layout = type_def["layout"] if type_def and "layout" in type_def else "generic"
    color = type_def["color"] if type_def else "#555"
    type_name = type_def["name"] if type_def else None

    view = {
        "equipment": equipment,
        "type_name": type_name,
        "color": color,
        "layout": layout,
    }

    if layout == "talent_pack_decoder":
        view["decoders"] = talent_pack_decoder_view(entry, equipment)
    else:
        labels = type_def["gpio_labels"] if type_def else device_types.default_labels()
        gpio_values = entry.get("gpio") or [None] * NUM_GPIO_GENERIC
        view["channels"] = list(zip(labels, gpio_values))

    return view


@app.route("/api/devices")
def api_devices():
    with devices_lock:
        return jsonify(devices)


@app.route("/api/registry")
def api_registry():
    return jsonify(registry.get_all())


@app.route("/api/device-types")
def api_device_types():
    return jsonify(device_types.get_all())


@app.route("/api/decoder-field", methods=["POST"])
def api_decoder_field():
    """Live-save endpoint for a single decoder field (name/frequency/
    receiver/log_enabled), called by the dashboard as the user types or
    toggles the "log this path" checkbox."""
    payload = request.get_json(silent=True) or {}
    mac = (payload.get("mac") or "").strip()
    decoder_index = payload.get("decoder_index")
    field = (payload.get("field") or "").strip()
    value = payload.get("value", "")

    if not mac or decoder_index is None or field not in ("name", "frequency", "receiver", "log_enabled"):
        return jsonify({"ok": False, "error": "invalid request"}), 400

    updated = registry.set_decoder_field(mac, int(decoder_index), field, value)
    if updated is None:
        return jsonify({"ok": False, "error": "unknown device"}), 404

    with devices_lock:
        for entry in devices.values():
            if entry.get("mac") and entry["mac"].upper() == mac.upper():
                entry["equipment"] = registry.get_equipment(entry["mac"])

    return jsonify({"ok": True})


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Equipment Dashboard</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    h1 { margin-bottom: 0.25rem; }
    .topbar { margin-bottom: 0.5rem; }
    .topbar a { color: #4caf50; margin-right: 1.5rem; text-decoration: none; }
    .topbar a:hover { text-decoration: underline; }
    .summary { color: #aaa; margin-bottom: 1.5rem; }
    .summary strong { color: #eee; }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 1rem;
    }
    .card {
      background: #1b1b1b;
      border: 1px solid #333;
      border-top: 4px solid var(--accent, #555);
      border-radius: 6px;
      padding: 12px 14px;
      transition: opacity 0.15s;
    }
    .card.card-wide { grid-column: span 2; min-width: 0; }
    .card.card-hidden { display: none !important; }
    .card-header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
    .card-title { font-size: 1.05rem; font-weight: bold; }
    .card-subtitle { color: #999; font-size: 0.8rem; margin-top: 2px; }
    .card-header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .badge { font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; font-weight: bold; white-space: nowrap; }
    .badge.online   { background: #1f3d24; color: #4caf50; }
    .badge.offline  { background: #3d1f1f; color: #f44336; }
    .badge.stale    { background: #3d2f1f; color: #ff9800; }
    .badge.unknown  { background: #2a2a2a; color: #999; }
    .hide-btn {
      background: none; border: 1px solid #333; color: #888; border-radius: 4px;
      width: 20px; height: 20px; line-height: 1; cursor: pointer; font-size: 13px;
      display: flex; align-items: center; justify-content: center; padding: 0;
    }
    .hide-btn:hover { background: #2a2a2a; color: #eee; }
    .unreg { color: #ff9800; font-style: italic; font-size: 0.85rem; }
    .unreg a { color: #4caf50; }
    .channels { margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; }
    .channel { display: flex; align-items: center; gap: 6px; font-size: 0.85rem; }
    .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    .dot.on  { background: #4caf50; box-shadow: 0 0 4px #4caf50; }
    .dot.off { background: #444; }
    .dot.na  { background: #222; border: 1px dashed #444; }
    .meta { margin-top: 10px; padding-top: 8px; border-top: 1px solid #292929; color: #777; font-size: 0.75rem; line-height: 1.5; }
    .empty { color: #777; margin-top: 2rem; }

    .tpd-decoders { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 10px; margin-top: 10px; }
    .tpd-decoder { background: #141414; border: 1px solid #2a2a2a; border-radius: 8px; padding: 10px; }
    .tpd-fields { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
    .tpd-fields input {
      width: 100%; background: #1e1e1e; border: 1px solid #333; border-radius: 4px;
      color: #eee; font-size: 12px; padding: 4px 6px; text-align: center; box-sizing: border-box;
    }
    .tpd-fields input.tpd-name { font-weight: 500; }
    .tpd-fields input.tpd-secondary { color: #999; }
    .tpd-log-toggle {
      display: flex; align-items: center; gap: 5px; font-size: 10px; color: #888;
      cursor: pointer; margin-top: 8px; padding-top: 6px; border-top: 1px solid #222;
    }
    .tpd-leds { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
    .tpd-led { display: flex; flex-direction: column; align-items: center; gap: 3px; }
    .tpd-led .dot { width: 13px; height: 13px; }
    .tpd-led-label { font-size: 9.5px; color: #999; text-align: center; white-space: nowrap; }
    .dot.led-green { background: #4caf50; box-shadow: 0 0 5px #4caf50; }
    .dot.led-yellow { background: #ffca28; box-shadow: 0 0 5px #ffca28; }
    .dot.led-red { background: #f44336; box-shadow: 0 0 5px #f44336; }
    .dot.led-blue { background: #42a5f5; box-shadow: 0 0 5px #42a5f5; }
    .dot.led-idle { background: #333; }

    .filter-bar { display: flex; align-items: center; gap: 1.5rem; margin-bottom: 1rem; font-size: 0.85rem; color: #aaa; }
    .filter-bar label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .filter-bar a { color: #4caf50; cursor: pointer; text-decoration: none; }
    .filter-bar a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h1>Equipment Dashboard</h1>
  <div class="topbar">
    <a href="/commission">+ Commission a device</a>
    <a href="/device-types">&#9881; Manage card types</a>
    <a href="/logs">&#128220; View logs</a>
  </div>
  <p class="summary" id="summary">
    <strong id="online-count">{{ online_count }}</strong> of
    <strong id="total-count">{{ total_count }}</strong> device(s) online.
  </p>
  <div class="filter-bar">
    <label><input type="checkbox" id="hide-offline-toggle"> Hide offline devices</label>
    <a id="show-hidden-link" style="display:none;" onclick="showAllHidden()"></a>
  </div>

  {% if devices|length == 0 %}
    <p class="empty">No devices seen yet. Power on an ESP32 unit and it'll appear here automatically.</p>
  {% endif %}

  <div class="cards" id="cards">
    {% for id, d in devices.items() %}
    {% set view = card_view(d) %}
    <div class="card {{ 'card-wide' if view.layout == 'talent_pack_decoder' else '' }}"
         style="--accent: {{ view.color }}" data-device-id="{{ id }}" data-status="{{ d.status }}">
      <div class="card-header">
        <div>
          <div class="card-title">
            {% if view.equipment %}{{ view.equipment.name }}{% else %}{{ id }}{% endif %}
          </div>
          <div class="card-subtitle">
            {% if view.type_name %}{{ view.type_name }}{% endif %}
            {% if view.equipment and view.equipment.location %} &middot; {{ view.equipment.location }}{% endif %}
          </div>
        </div>
        <div class="card-header-right">
          <span class="badge {{ d.status }}" data-role="status-badge">{{ d.status }}</span>
          <button class="hide-btn" title="Hide this card" onclick="hideCard('{{ id }}')">&times;</button>
        </div>
      </div>

      {% if not view.equipment %}
        <p class="unreg">
          unregistered
          {% if d.mac %}&mdash; <a href="/commission?mac={{ d.mac }}">register it</a>{% endif %}
        </p>
      {% endif %}

      {% if view.layout == "talent_pack_decoder" %}
        <div class="tpd-decoders">
          {% for dec in view.decoders %}
          <div class="tpd-decoder" data-decoder-index="{{ dec.index }}">
            <div class="tpd-fields">
              <input class="tpd-name" type="text" placeholder="Name" value="{{ dec.name }}"
                     data-mac="{{ d.mac }}" data-decoder-index="{{ dec.index }}" data-field="name">
              <input class="tpd-secondary" type="text" placeholder="Frequency" value="{{ dec.frequency }}"
                     data-mac="{{ d.mac }}" data-decoder-index="{{ dec.index }}" data-field="frequency">
              <input class="tpd-secondary" type="text" placeholder="Receiver" value="{{ dec.receiver }}"
                     data-mac="{{ d.mac }}" data-decoder-index="{{ dec.index }}" data-field="receiver">
            </div>
            <div class="tpd-leds">
              <div class="tpd-led">
                <div class="dot {{ 'led-green' if dec.on_air == 1 else 'led-idle' }}" data-role="led-on_air"></div>
                <div class="tpd-led-label">On-Air</div>
              </div>
              <div class="tpd-led">
                <div class="dot {{ 'led-yellow' if dec.prod == 1 else 'led-idle' }}" data-role="led-prod"></div>
                <div class="tpd-led-label">Prod</div>
              </div>
              <div class="tpd-led">
                <div class="dot {{ 'led-red' if dec.err_man_state == 'error' else ('led-blue' if dec.err_man_state == 'manual' else 'led-idle') }}" data-role="led-errman"></div>
                <div class="tpd-led-label">Error/Man</div>
              </div>
              <div class="tpd-led">
                <div class="dot {{ 'led-red' if dec.call == 1 else 'led-idle' }}" data-role="led-call"></div>
                <div class="tpd-led-label">Call</div>
              </div>
            </div>
            <label class="tpd-log-toggle">
              <input type="checkbox" data-mac="{{ d.mac }}" data-decoder-index="{{ dec.index }}"
                     data-field="log_enabled" {{ 'checked' if dec.log_enabled else '' }}>
              Log this path
            </label>
          </div>
          {% endfor %}
        </div>
      {% else %}
        <div class="channels">
          {% for label, val in view.channels %}
          <div class="channel">
            <span class="dot {{ 'on' if val == 1 else ('off' if val == 0 else 'na') }}" data-role="channel-{{ loop.index0 }}"></span>
            <span>{{ label }}</span>
          </div>
          {% endfor %}
        </div>
      {% endif %}

      <div class="meta">
        Device ID: {{ id }}<br>
        MAC: {{ d.mac or "-" }} &middot; IP: {{ d.ip or "-" }}<br>
        Last seen: <span data-role="last-seen">{{ d.last_seen or "-" }}</span> UTC
      </div>
    </div>
    {% endfor %}
  </div>

  <script>
    // ---- Card visibility: hide-offline toggle + per-card manual hide ----
    // Both preferences are per-browser (localStorage), not server-side —
    // "what I want to see on this screen" isn't shared server state.
    const HIDE_OFFLINE_KEY = 'gpio_monitor_hide_offline';
    const HIDDEN_CARDS_KEY = 'gpio_monitor_hidden_cards';

    function getHiddenSet() {
      try {
        return new Set(JSON.parse(localStorage.getItem(HIDDEN_CARDS_KEY) || '[]'));
      } catch (e) { return new Set(); }
    }
    function saveHiddenSet(set) {
      localStorage.setItem(HIDDEN_CARDS_KEY, JSON.stringify(Array.from(set)));
    }
    function hideCard(deviceId) {
      const hidden = getHiddenSet();
      hidden.add(deviceId);
      saveHiddenSet(hidden);
      applyFilters();
    }
    function showAllHidden() {
      saveHiddenSet(new Set());
      applyFilters();
    }

    function applyFilters() {
      const hideOffline = document.getElementById('hide-offline-toggle').checked;
      const hidden = getHiddenSet();
      let visibleShown = 0;

      document.querySelectorAll('.card').forEach(function (card) {
        const id = card.dataset.deviceId;
        const status = card.dataset.status;
        const manuallyHidden = hidden.has(id);
        const offlineHidden = hideOffline && status !== 'online';
        card.classList.toggle('card-hidden', manuallyHidden || offlineHidden);
      });

      const link = document.getElementById('show-hidden-link');
      if (hidden.size > 0) {
        link.style.display = '';
        link.textContent = hidden.size + ' card(s) manually hidden — show all';
      } else {
        link.style.display = 'none';
      }
    }

    document.getElementById('hide-offline-toggle').addEventListener('change', function (e) {
      localStorage.setItem(HIDE_OFFLINE_KEY, e.target.checked ? '1' : '0');
      applyFilters();
    });

    // Restore saved toggle state on load
    document.getElementById('hide-offline-toggle').checked = localStorage.getItem(HIDE_OFFLINE_KEY) === '1';
    applyFilters();

    // Debounced live-save for decoder text fields — fires shortly after the
    // user stops typing, so it doesn't spam the server on every keystroke.
    let saveTimers = {};
    document.getElementById('cards').addEventListener('input', function (e) {
      const el = e.target;
      if (!el.matches('input[type="text"][data-field]')) return;
      const key = el.dataset.mac + ':' + el.dataset.decoderIndex + ':' + el.dataset.field;
      clearTimeout(saveTimers[key]);
      saveTimers[key] = setTimeout(function () {
        fetch('/api/decoder-field', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mac: el.dataset.mac,
            decoder_index: parseInt(el.dataset.decoderIndex, 10),
            field: el.dataset.field,
            value: el.value
          })
        }).catch(function (err) { console.error('decoder-field save failed', err); });
      }, 500);
    });

    // The "log this path" checkbox saves immediately on toggle — no debounce
    // needed for a single click, and no reason to wait.
    document.getElementById('cards').addEventListener('change', function (e) {
      const el = e.target;
      if (!el.matches('input[type="checkbox"][data-field="log_enabled"]')) return;
      fetch('/api/decoder-field', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mac: el.dataset.mac,
          decoder_index: parseInt(el.dataset.decoderIndex, 10),
          field: el.dataset.field,
          value: el.checked
        })
      }).catch(function (err) { console.error('log_enabled save failed', err); });
    });

    // Background poll: updates LED/status/last-seen only, never touches the
    // text inputs, so it can never interrupt someone mid-edit.
    function applyLedClass(dotEl, on, colorClass) {
      dotEl.classList.remove('on', 'off', 'na', 'led-green', 'led-yellow', 'led-red', 'led-blue', 'led-idle');
      dotEl.classList.add(on ? colorClass : (colorClass.startsWith('led-') ? 'led-idle' : 'off'));
    }

    async function pollDevices() {
      try {
        const res = await fetch('/api/devices');
        const data = await res.json();
        let onlineCount = 0;
        const total = Object.keys(data).length;

        for (const [id, d] of Object.entries(data)) {
          if (d.status === 'online') onlineCount++;
          const card = document.querySelector('.card[data-device-id="' + CSS.escape(id) + '"]');
          if (!card) continue;

          const badge = card.querySelector('[data-role="status-badge"]');
          if (badge) {
            badge.textContent = d.status;
            badge.className = 'badge ' + d.status;
          }
          card.dataset.status = d.status;
          const lastSeen = card.querySelector('[data-role="last-seen"]');
          if (lastSeen) lastSeen.textContent = d.last_seen || '-';

          const gpio = d.gpio || [];
          const tpdDecoders = card.querySelectorAll('.tpd-decoder');
          if (tpdDecoders.length) {
            tpdDecoders.forEach(function (decEl, i) {
              const base = i * 5;
              const onAir = gpio[base], prod = gpio[base + 1];
              const errA = gpio[base + 2], errB = gpio[base + 3], call = gpio[base + 4];
              applyLedClass(decEl.querySelector('[data-role="led-on_air"]'), onAir === 1, 'led-green');
              applyLedClass(decEl.querySelector('[data-role="led-prod"]'), prod === 1, 'led-yellow');
              const errManDot = decEl.querySelector('[data-role="led-errman"]');
              errManDot.classList.remove('led-red', 'led-blue', 'led-idle');
              if (errA === 1) errManDot.classList.add('led-red');
              else if (errB === 1) errManDot.classList.add('led-blue');
              else errManDot.classList.add('led-idle');
              applyLedClass(decEl.querySelector('[data-role="led-call"]'), call === 1, 'led-red');
            });
          } else {
            const dots = card.querySelectorAll('[data-role^="channel-"]');
            dots.forEach(function (dotEl, i) {
              dotEl.classList.remove('on', 'off', 'na');
              const v = gpio[i];
              dotEl.classList.add(v === 1 ? 'on' : (v === 0 ? 'off' : 'na'));
            });
          }
        }

        document.getElementById('online-count').textContent = onlineCount;
        document.getElementById('total-count').textContent = total;
        applyFilters();
      } catch (err) {
        console.error('poll failed', err);
      }
    }
    setInterval(pollDevices, 3000);
  </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    with devices_lock:
        snapshot = dict(devices)
    online_count = sum(1 for d in snapshot.values() if d["status"] == "online")
    return render_template_string(
        DASHBOARD_HTML,
        devices=snapshot,
        online_count=online_count,
        total_count=len(snapshot),
        card_view=card_view,
    )


COMMISSION_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Commission Device</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    label { display: block; margin-top: 1rem; }
    input, select { width: 100%; max-width: 400px; padding: 6px; margin-top: 4px; }
    button { margin-top: 1.5rem; padding: 8px 16px; }
    a { color: #4caf50; }
    table { border-collapse: collapse; width: 100%; margin-top: 2rem; }
    th, td { border: 1px solid #444; padding: 8px 12px; text-align: left; }
    th { background: #222; }
    form.inline { display: inline; }
  </style>
</head>
<body>
  <p><a href="/">&larr; back to dashboard</a></p>
  <h1>{% if prefill_entry %}Edit Device{% else %}Commission a Device{% endif %}</h1>
  <p>Enter the ESP32's MAC address (printed in Serial Monitor on boot, or
     visible on the dashboard once it has connected at least once), the
     equipment it's attached to, and which card type it should use.</p>
  <form method="POST" action="/commission">
    <label>MAC Address
      <input type="text" name="mac" placeholder="AA:BB:CC:DD:EE:FF" value="{{ prefill_mac or '' }}"
             {{ 'readonly' if prefill_entry else '' }} required>
      {% if prefill_entry %}<small style="color:#888;">Editing existing device &mdash; MAC can't be changed here (it's the record's key). Delete and re-commission if it needs to change.</small>{% endif %}
    </label>
    <label>Equipment Name
      <input type="text" name="name" placeholder="e.g. Compressor Panel 3"
             value="{{ prefill_entry.name if prefill_entry else '' }}" required>
    </label>
    <label>Card Type
      <select name="device_type">
        <option value="">-- none (generic GPIO labels) --</option>
        {% for tid, t in types_sorted %}
        <option value="{{ tid }}" {{ 'selected' if prefill_entry and prefill_entry.device_type == tid else '' }}>{{ tid }}: {{ t.name }}</option>
        {% endfor %}
      </select>
    </label>
    <label>Location (optional)
      <input type="text" name="location" placeholder="e.g. Building 2, Rack 4"
             value="{{ prefill_entry.location if prefill_entry else '' }}">
    </label>
    <label>Notes (optional)
      <input type="text" name="notes" placeholder="e.g. LED 7 = fault indicator"
             value="{{ prefill_entry.notes if prefill_entry else '' }}">
    </label>
    <button type="submit">Save</button>
  </form>
  <p style="margin-top:1rem;"><a href="/device-types">Need a new card type first? Manage card types &rarr;</a></p>

  <h2>Registered Devices</h2>
  <table>
    <tr><th>MAC</th><th>Equipment</th><th>Card Type</th><th>Location</th><th>Notes</th><th>Commissioned</th><th></th></tr>
    {% for mac, e in reg.items() %}
    <tr>
      <td>{{ mac }}</td>
      <td>{{ e.name }}</td>
      <td>{% if e.device_type and types.get(e.device_type) %}{{ types[e.device_type].name }}{% else %}-{% endif %}</td>
      <td>{{ e.location or "-" }}</td>
      <td>{{ e.notes or "-" }}</td>
      <td>{{ e.commissioned_at }}</td>
      <td>
        <a href="/commission?mac={{ mac }}">Edit</a> &middot;
        <form class="inline" method="POST" action="/commission/delete">
          <input type="hidden" name="mac" value="{{ mac }}">
          <button type="submit" onclick="return confirm('Remove this entry?')">Delete</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""


@app.route("/commission", methods=["GET"])
def commission_form():
    prefill_mac = request.args.get("mac", "")
    prefill_entry = registry.get_equipment(prefill_mac) if prefill_mac else None
    all_types = device_types.get_all()
    types_sorted = sorted(all_types.items(), key=lambda item: int(item[0]))
    return render_template_string(
        COMMISSION_HTML,
        reg=registry.get_all(),
        types=all_types,
        types_sorted=types_sorted,
        prefill_mac=prefill_mac,
        prefill_entry=prefill_entry,
    )


@app.route("/commission", methods=["POST"])
def commission_save():
    mac = request.form.get("mac", "").strip()
    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    notes = request.form.get("notes", "").strip()
    dtype = request.form.get("device_type", "").strip()

    if mac and name:
        registry.upsert(mac, name, location, notes, dtype)
        # refresh any already-connected device that matches this MAC
        with devices_lock:
            for entry in devices.values():
                if entry.get("mac") and entry["mac"].upper() == mac.upper():
                    entry["equipment"] = registry.get_equipment(entry["mac"])

    return redirect(url_for("commission_form"))


@app.route("/commission/delete", methods=["POST"])
def commission_delete():
    mac = request.form.get("mac", "").strip()
    if mac:
        registry.delete(mac)
        with devices_lock:
            for entry in devices.values():
                if entry.get("mac") and entry["mac"].upper() == mac.upper():
                    entry["equipment"] = None
    return redirect(url_for("commission_form"))


DEVICE_TYPES_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Manage Card Types</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    a { color: #4caf50; }
    table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
    th, td { border: 1px solid #444; padding: 6px 10px; text-align: left; font-size: 0.9rem; }
    th { background: #222; }
    .swatch { width: 16px; height: 16px; border-radius: 3px; display: inline-block; vertical-align: middle; }
    form.inline { display: inline; }
    .edit-form { background: #1b1b1b; border: 1px solid #333; border-radius: 6px; padding: 16px; margin-top: 1.5rem; max-width: 600px; }
    .edit-form label { display: block; margin-top: 0.75rem; font-size: 0.9rem; }
    .edit-form input[type=text] { width: 100%; padding: 5px; margin-top: 3px; }
    .edit-form input[type=color] { margin-top: 3px; }
    .label-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem 1rem; margin-top: 0.5rem; }
    .label-grid label { margin-top: 0; }
    button { margin-top: 1.25rem; padding: 8px 16px; }
    .empty-row { color: #666; }
    .special-note { color: #ff9800; font-size: 0.85rem; margin-top: 0.5rem; }
  </style>
</head>
<body>
  <p><a href="/">&larr; back to dashboard</a></p>
  <h1>Manage Card Types</h1>
  <p>Up to 32 reusable card templates. Each one names the equipment
     category and labels what each GPIO channel means for that type.
     Assign a type to a device on the <a href="/commission">commission page</a>.</p>

  <table>
    <tr><th>#</th><th>Name</th><th>Color</th><th>Layout</th><th></th></tr>
    {% for i in range(1, 33) %}
    {% set tid = i|string %}
    {% set t = types.get(tid) %}
    <tr>
      <td>{{ i }}</td>
      {% if t %}
        <td>{{ t.name }}</td>
        <td><span class="swatch" style="background:{{ t.color }}"></span> {{ t.color }}</td>
        <td>{{ t.layout if t.layout and t.layout != "generic" else "generic (per-GPIO labels)" }}</td>
        <td>
          <a href="/device-types?edit={{ tid }}">Edit</a> &middot;
          <form class="inline" method="POST" action="/device-types/delete">
            <input type="hidden" name="type_id" value="{{ tid }}">
            <button type="submit" onclick="return confirm('Delete this card type? Devices using it will fall back to generic GPIO labels.')">Delete</button>
          </form>
        </td>
      {% else %}
        <td class="empty-row" colspan="2">&mdash; empty slot &mdash;</td>
        <td class="empty-row">-</td>
        <td><a href="/device-types?edit={{ tid }}">Define</a></td>
      {% endif %}
    </tr>
    {% endfor %}
  </table>

  {% if edit_id %}
  <div class="edit-form">
    <h2>{% if edit_type %}Edit{% else %}Define{% endif %} type #{{ edit_id }}</h2>
    {% if edit_type and edit_type.layout and edit_type.layout != "generic" %}
    <p class="special-note">This type uses a special built-in card layout ({{ edit_type.layout }}) &mdash;
       only its name and color are editable here; the card structure itself is defined in code.</p>
    {% endif %}
    <form method="POST" action="/device-types">
      <input type="hidden" name="type_id" value="{{ edit_id }}">
      <label>Name
        <input type="text" name="name" value="{{ edit_type.name if edit_type else '' }}" placeholder="e.g. Compressor Panel" required>
      </label>
      <label>Accent color
        <input type="color" name="color" value="{{ edit_type.color if edit_type else '#4caf50' }}">
      </label>
      {% if not edit_type or not edit_type.layout or edit_type.layout == "generic" %}
      <div class="label-grid">
        {% for i in range(12) %}
        <label>GPIO {{ i }} label
          <input type="text" name="label_{{ i }}"
                 value="{{ edit_type.gpio_labels[i] if edit_type else '' }}"
                 placeholder="GPIO {{ i }}">
        </label>
        {% endfor %}
      </div>
      {% endif %}
      <button type="submit">Save type</button>
    </form>
  </div>
  {% endif %}
</body>
</html>
"""


@app.route("/device-types", methods=["GET"])
def device_types_page():
    edit_id = request.args.get("edit", "")
    edit_type = device_types.get_type(edit_id) if edit_id else None
    return render_template_string(
        DEVICE_TYPES_HTML,
        types=device_types.get_all(),
        edit_id=edit_id,
        edit_type=edit_type,
    )


@app.route("/device-types", methods=["POST"])
def device_types_save():
    type_id = request.form.get("type_id", "").strip()
    name = request.form.get("name", "").strip()
    color = request.form.get("color", "").strip()

    existing = device_types.get_type(type_id)
    layout = existing["layout"] if existing and "layout" in existing else "generic"

    if layout == "generic":
        labels = [request.form.get(f"label_{i}", "").strip() or f"GPIO {i}" for i in range(12)]
    else:
        labels = existing.get("gpio_labels", device_types.default_labels())

    if type_id and name:
        try:
            device_types.upsert(type_id, name, labels, color, layout)
        except ValueError as e:
            print(f"device-types save error: {e}")

    return redirect(url_for("device_types_page"))


@app.route("/device-types/delete", methods=["POST"])
def device_types_delete():
    type_id = request.form.get("type_id", "").strip()
    if type_id:
        device_types.delete(type_id)
    return redirect(url_for("device_types_page"))


LOGS_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Event Logs</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    a { color: #4caf50; }
    .layout { display: flex; gap: 2rem; align-items: flex-start; }
    .dates { min-width: 160px; }
    .dates ul { list-style: none; padding: 0; margin: 0.5rem 0; }
    .dates li { margin-bottom: 4px; }
    .dates a.active { color: #eee; font-weight: bold; }
    .dates .empty { color: #666; font-size: 0.85rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #444; padding: 6px 10px; text-align: left; font-size: 0.85rem; }
    th { background: #222; }
    .state-1 { color: #4caf50; font-weight: bold; }
    .state-0 { color: #f44336; font-weight: bold; }
    .content { flex: 1; }
    .empty-state { color: #777; }
    .retention-note { color: #666; font-size: 0.8rem; margin-top: 1rem; }
  </style>
</head>
<body>
  <p><a href="/">&larr; back to dashboard</a></p>
  <h1>Event Logs</h1>
  <p>On-Air / Prod state changes for any decoder path with "Log this path"
     checked on its card. One file per day; kept for 30 days automatically.</p>

  <div class="layout">
    <div class="dates">
      <strong>Dates</strong>
      {% if dates|length == 0 %}
        <p class="empty">No logs yet.</p>
      {% else %}
      <ul>
        {% for d in dates %}
        <li><a href="/logs?date={{ d }}" class="{{ 'active' if d == selected_date else '' }}">{{ d }}</a></li>
        {% endfor %}
      </ul>
      {% endif %}
    </div>
    <div class="content">
      {% if selected_date %}
        <p>
          <strong>{{ selected_date }}</strong> &middot; {{ rows|length }} event(s)
          &middot; <a href="/logs/download/{{ selected_date }}">Download CSV</a>
        </p>
        {% if rows|length == 0 %}
          <p class="empty-state">No events recorded for this date.</p>
        {% else %}
        <table>
          <tr><th>Time (UTC)</th><th>Equipment</th><th>Decoder</th><th>Channel</th><th>State</th></tr>
          {% for row in rows %}
          <tr>
            <td>{{ row.timestamp }}</td>
            <td>{{ row.device_id }}</td>
            <td>{{ row.decoder_name }}</td>
            <td>{{ row.channel }}</td>
            <td class="state-{{ row.state }}">{{ 'ON' if row.state == '1' else 'OFF' }}</td>
          </tr>
          {% endfor %}
        </table>
        {% endif %}
      {% else %}
        <p class="empty-state">Select a date to view its events.</p>
      {% endif %}
      <p class="retention-note">Log files older than 30 days are deleted automatically.</p>
    </div>
  </div>
</body>
</html>
"""


@app.route("/logs")
def logs_page():
    selected_date = request.args.get("date", "")
    dates = event_log.list_log_files()
    rows = event_log.read_log_file(selected_date) if selected_date else []
    return render_template_string(
        LOGS_HTML, dates=dates, selected_date=selected_date, rows=rows
    )


@app.route("/logs/download/<date_str>")
def logs_download(date_str):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return "Invalid date", 400
    path = event_log.log_file_path(date_str)
    if not path:
        return "Log file not found", 404
    return send_file(path, as_attachment=True, download_name=f"gpio-events-{date_str}.csv")


def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


if __name__ == "__main__":
    start_mqtt()
    threading.Thread(target=stale_checker, daemon=True).start()
    event_log.start_cleanup_thread()
    app.run(host="0.0.0.0", port=WEB_PORT)
