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
    with open(REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
            "commissioned_at": existing.get(
                "commissioned_at", datetime.now(timezone.utc).isoformat()
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)
    return data[mac]


def set_decoder_field(mac: str, decoder_index: int, field: str, value):
    """Live-edit a single field (name/frequency/receiver/log_enabled) for
    one decoder group on a commissioned device, without touching anything
    else on its registry entry. Used by the dashboard's inline-editable
    card fields and the "log this path" checkbox."""
    if field not in ("name", "frequency", "receiver", "log_enabled"):
        raise ValueError(f"Unknown decoder field: {field}")
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        if mac not in data:
            return None
        decoders = data[mac].setdefault("decoders", [])
        while len(decoders) <= decoder_index:
            decoders.append({"name": "", "frequency": "", "receiver": "", "log_enabled": False})
        decoders[decoder_index][field] = value
        data[mac]["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save(data)
    return data[mac]


def delete(mac: str):
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        if mac in data:
            del data[mac]
            _save(data)
