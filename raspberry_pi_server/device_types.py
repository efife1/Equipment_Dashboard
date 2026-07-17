"""
Device "type" definitions for the dashboard.

A type is a reusable card template: a name, an accent color, and a label
for each of the 12 monitored GPIO channels (e.g. "Pump Running" instead of
a bare "GPIO 3"). Up to 32 types are supported. Equipment is linked to a
type during commissioning (see registry.py's device_type field), and the
dashboard renders each device's card using its assigned type's labels.

Stored as JSON on disk so entries survive server restarts.
"""

import json
import os
import threading
from datetime import datetime, timezone

TYPES_FILE = os.path.join(os.path.dirname(__file__), "device_types.json")
MAX_TYPES = 32
NUM_GPIO = 12
DEFAULT_COLOR = "#4caf50"

_lock = threading.Lock()


def _load():
    if not os.path.exists(TYPES_FILE):
        return {}
    with open(TYPES_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save(data):
    with open(TYPES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_all():
    """Returns all defined types as {type_id_str: {...}}."""
    with _lock:
        return _load()


def get_type(type_id):
    """Returns a single type's definition, or None if unset/unassigned."""
    if not type_id:
        return None
    with _lock:
        data = _load()
    return data.get(str(type_id))


def default_labels():
    return [f"GPIO {i}" for i in range(NUM_GPIO)]


def upsert(type_id, name, gpio_labels, color=DEFAULT_COLOR, layout="generic"):
    """Create or update one of the 32 type slots.
    layout is "generic" (the default label-grid card) or a special layout
    keyword (e.g. "talent_pack_decoder") that tells the dashboard to use a
    bespoke card renderer instead of the generic per-GPIO label grid."""
    type_id = str(type_id)
    if not type_id.isdigit() or not (1 <= int(type_id) <= MAX_TYPES):
        raise ValueError(f"type_id must be an integer from 1 to {MAX_TYPES}")

    labels = list(gpio_labels)[:NUM_GPIO]
    while len(labels) < NUM_GPIO:
        labels.append(f"GPIO {len(labels)}")

    with _lock:
        data = _load()
        existing = data.get(type_id, {})
        data[type_id] = {
            "name": name,
            "gpio_labels": labels,
            "color": color or DEFAULT_COLOR,
            "layout": layout or "generic",
            "created_at": existing.get(
                "created_at", datetime.now(timezone.utc).isoformat()
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(data)
    return data[type_id]


def ensure_builtin_types():
    """Seeds built-in special-layout types on first run, if not already
    present (e.g. if a user hasn't defined/overwritten slot 1 themselves)."""
    with _lock:
        data = _load()
        if "1" not in data:
            data["1"] = {
                "name": "Talent Pack Decoder",
                "gpio_labels": default_labels(),
                "color": "#4caf50",
                "layout": "talent_pack_decoder",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _save(data)


def delete(type_id):
    type_id = str(type_id)
    with _lock:
        data = _load()
        if type_id in data:
            del data[type_id]
            _save(data)
