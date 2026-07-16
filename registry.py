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


def upsert(mac: str, name: str, location: str = "", notes: str = ""):
    """Add or update a commissioning entry for a MAC address."""
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        existing = data.get(mac, {})
        data[mac] = {
            "name": name,
            "location": location,
            "notes": notes,
            "commissioned_at": existing.get(
                "commissioned_at", datetime.now(timezone.utc).isoformat()
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)
    return data[mac]


def delete(mac: str):
    mac = _normalize_mac(mac)
    with _lock:
        data = _load()
        if mac in data:
            del data[mac]
            _save(data)
