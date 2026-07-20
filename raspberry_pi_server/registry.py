"""
Simple persistent MAC address -> equipment registry.
Stored as JSON on disk so entries survive server restarts.
"""

import json
import os
import threading
from datetime import datetime, timezone

REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "registry.json")

_lock = threading.Lock()


def _normalize_mac(mac: str) -> str:
    return mac.strip().upper()


def _load():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    with open(REGISTRY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data):
    # Atomic write: write to a temp file in the same directory, then rename
    # over the real file. os.replace() is atomic on POSIX, so a crash or
    # power loss mid-write leaves the original file intact rather than
    # truncated/corrupted — a truncated JSON file would otherwise silently
    # read back as {} (see _load()), losing every commissioned device.
    tmp_path = REGISTRY_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, REGISTRY_FILE)


def get_all():
    with _lock:
        return _load()


def get_equipment(mac: str):
    """Returns the registry entry for a MAC address, or None if unregistered."""
    if not mac:
        return None
    with _lock:
        data = _load()
    return data.get(_normalize_mac(mac))


def upsert(mac: str, name: str, location: str = "", notes: str = "", device_type: str = ""):
    """Add or update a commissioning entry for a MAC address.
    device_type references a slot ID (1-32) from device_types.py, controlling
    which card template is used to render this device on the dashboard."""
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        existing = data.get(mac, {})
        data[mac] = {
            "name": name,
            "location": location,
            "notes": notes,
            "device_type": device_type,
            "decoders": existing.get("decoders", []),
            "paths": existing.get("paths", []),
            "commissioned_at": existing.get(
                "commissioned_at", datetime.now(timezone.utc).isoformat()
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)
    return data[mac]


def _set_group_field(mac: str, list_field: str, group_index: int, field: str, value, default_item: dict):
    """Shared logic for live-editing one field within one item of a
    per-device list of sub-groups (e.g. one decoder on a Talent Pack
    Decoder, or one path on a Fiber Drawer) — pads the list with
    default_item as needed, updates just the one field, leaves everything
    else on the registry entry untouched."""
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        if mac not in data:
            return None
        items = data[mac].setdefault(list_field, [])
        while len(items) <= group_index:
            items.append(dict(default_item))
        items[group_index][field] = value
        data[mac]["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)
    return data[mac]


def set_decoder_field(mac: str, decoder_index: int, field: str, value):
    """Live-edit a single field (name/frequency/receiver/log_enabled) for
    one decoder group on a Talent Pack Decoder. Used by the dashboard's
    inline-editable card fields and the "log this path" checkbox."""
    if field not in ("name", "frequency", "receiver", "log_enabled"):
        raise ValueError(f"Unknown decoder field: {field}")
    return _set_group_field(mac, "decoders", decoder_index, field, value,
                             {"name": "", "frequency": "", "receiver": "", "log_enabled": False})


def set_path_field(mac: str, path_index: int, field: str, value):
    """Live-edit a single field (name/reference) for one path on a Fiber
    Drawer. "reference" is normally set via set_path_reference() below
    (captured from a live reading) rather than typed directly, but both
    go through the same underlying storage."""
    if field not in ("name", "reference"):
        raise ValueError(f"Unknown path field: {field}")
    return _set_group_field(mac, "paths", path_index, field, value,
                             {"name": "", "reference": None})


def set_path_reference(mac: str, path_index: int, value):
    """Captures a live reading as the saved reference/baseline for one
    Fiber Drawer path, so future readings can be compared against it."""
    return set_path_field(mac, path_index, "reference", value)


def delete(mac: str):
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        if mac in data:
            del data[mac]
            _save(data)
