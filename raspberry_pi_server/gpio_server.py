"""
Raspberry Pi GPIO Monitor Server
---------------------------------
Subscribes to MQTT topics published by ESP32 GPIO client devices,
cross-references each device's MAC address against a commissioning
registry (registry.py / registry.json) to show what equipment it's
attached to, and exposes it all via a small Flask web dashboard/API.

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
   Raw JSON:                http://<pi-ip>:8080/api/devices
"""

import json
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template_string, request, redirect, url_for

import registry

# ================= CONFIG =================
MQTT_BROKER = "localhost"       # broker running on this same Pi
MQTT_PORT = 1883
MQTT_STATUS_TOPIC = "gpio/+/status"
MQTT_LWT_TOPIC = "gpio/+/lwt"
STALE_TIMEOUT_SEC = 30           # mark a device offline if silent this long
WEB_PORT = 8080
# ============================================

app = Flask(__name__)
devices = {}
devices_lock = threading.Lock()


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
                entry["gpio"] = payload.get("gpio")
                entry["ip"] = payload.get("ip")
                entry["mac"] = payload.get("mac")
                entry["last_seen"] = now_iso()
                entry["status"] = "online"
                entry["equipment"] = registry.get_equipment(entry["mac"])
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


@app.route("/api/devices")
def api_devices():
    with devices_lock:
        return jsonify(devices)


@app.route("/api/registry")
def api_registry():
    return jsonify(registry.get_all())


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>GPIO Monitor</title>
  <meta http-equiv="refresh" content="3">
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #444; padding: 8px 12px; text-align: left; }
    th { background: #222; }
    .online   { color: #4caf50; font-weight: bold; }
    .offline  { color: #f44336; font-weight: bold; }
    .stale    { color: #ff9800; font-weight: bold; }
    .unknown  { color: #999; font-weight: bold; }
    .bit-on   { color: #4caf50; padding: 0 2px; }
    .bit-off  { color: #555; padding: 0 2px; }
    .unreg    { color: #ff9800; font-style: italic; }
    a.btn { color: #4caf50; text-decoration: none; }
    .topbar { margin-bottom: 1rem; }
    .topbar a { color: #4caf50; margin-right: 1rem; }
  </style>
</head>
<body>
  <h1>ESP32 GPIO Monitor</h1>
  <div class="topbar"><a href="/commission">+ Commission a device</a></div>
  <p>{{ devices|length }} device(s) seen. Auto-refreshes every 3s.</p>
  <table>
    <tr><th>Equipment</th><th>Device ID</th><th>MAC</th><th>Status</th><th>IP</th><th>Last Seen (UTC)</th><th>GPIO States</th></tr>
    {% for id, d in devices.items() %}
    <tr>
      <td>
        {% if d.equipment %}
          {{ d.equipment.name }}{% if d.equipment.location %} <small>({{ d.equipment.location }})</small>{% endif %}
        {% else %}
          <span class="unreg">unregistered</span>
          {% if d.mac %}<br><a class="btn" href="/commission?mac={{ d.mac }}">register it</a>{% endif %}
        {% endif %}
      </td>
      <td>{{ id }}</td>
      <td>{{ d.mac or "-" }}</td>
      <td class="{{ d.status }}">{{ d.status }}</td>
      <td>{{ d.ip or "-" }}</td>
      <td>{{ d.last_seen or "-" }}</td>
      <td>
        {% if d.gpio %}
          {% for bit in d.gpio %}<span class="{{ 'bit-on' if bit else 'bit-off' }}">{{ bit }}</span>{% endfor %}
        {% else %}-{% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
</body>
</html>
"""


@app.route("/")
def dashboard():
    with devices_lock:
        return render_template_string(DASHBOARD_HTML, devices=devices)


COMMISSION_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Commission Device</title>
  <style>
    body { font-family: sans-serif; margin: 2rem; background:#111; color:#eee; }
    label { display: block; margin-top: 1rem; }
    input { width: 100%; max-width: 400px; padding: 6px; margin-top: 4px; }
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
  <h1>Commission a Device</h1>
  <p>Enter the ESP32's MAC address (printed in Serial Monitor on boot, or
     visible on the dashboard once it has connected at least once) and the
     equipment it's attached to.</p>
  <form method="POST" action="/commission">
    <label>MAC Address
      <input type="text" name="mac" placeholder="AA:BB:CC:DD:EE:FF" value="{{ prefill_mac or '' }}" required>
    </label>
    <label>Equipment Name
      <input type="text" name="name" placeholder="e.g. Compressor Panel 3" required>
    </label>
    <label>Location (optional)
      <input type="text" name="location" placeholder="e.g. Building 2, Rack 4">
    </label>
    <label>Notes (optional)
      <input type="text" name="notes" placeholder="e.g. LED 7 = fault indicator">
    </label>
    <button type="submit">Save</button>
  </form>

  <h2>Registered Devices</h2>
  <table>
    <tr><th>MAC</th><th>Equipment</th><th>Location</th><th>Notes</th><th>Commissioned</th><th></th></tr>
    {% for mac, e in reg.items() %}
    <tr>
      <td>{{ mac }}</td>
      <td>{{ e.name }}</td>
      <td>{{ e.location or "-" }}</td>
      <td>{{ e.notes or "-" }}</td>
      <td>{{ e.commissioned_at }}</td>
      <td>
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
    return render_template_string(
        COMMISSION_HTML, reg=registry.get_all(), prefill_mac=prefill_mac
    )


@app.route("/commission", methods=["POST"])
def commission_save():
    mac = request.form.get("mac", "").strip()
    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    notes = request.form.get("notes", "").strip()

    if mac and name:
        registry.upsert(mac, name, location, notes)
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
    app.run(host="0.0.0.0", port=WEB_PORT)
