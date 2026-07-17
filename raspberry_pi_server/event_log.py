"""
CSV event logger for On-Air / Prod state changes on Talent Pack Decoder
paths the user has opted into (the "Log this path" checkbox on each
decoder). One CSV file per calendar day, named YYYY-MM-DD.csv, written to
the logs/ subfolder. Files older than RETENTION_DAYS from today are
deleted automatically by a background thread.
"""

import csv
import os
import time
import threading
from datetime import datetime, timezone, timedelta

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
RETENTION_DAYS = 30
FIELDNAMES = ["timestamp", "device_id", "mac", "decoder_name", "channel", "state"]

_lock = threading.Lock()


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _today_filename():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".csv"


def log_event(device_id, mac, decoder_name, channel, state):
    """Appends one row to today's log file, creating it (with header) if
    this is the first event logged today."""
    _ensure_log_dir()
    path = os.path.join(LOG_DIR, _today_filename())
    with _lock:
        is_new = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if is_new:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "device_id": device_id,
                "mac": mac or "",
                "decoder_name": decoder_name or "",
                "channel": channel,
                "state": state,
            })


def list_log_files():
    """Returns available log dates (YYYY-MM-DD strings), newest first."""
    _ensure_log_dir()
    files = [f[:-4] for f in os.listdir(LOG_DIR) if f.endswith(".csv")]
    files.sort(reverse=True)
    return files


def read_log_file(date_str):
    """Returns a list of row dicts for the given date (newest first), or
    [] if the date is invalid or has no log file."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []
    _ensure_log_dir()
    path = os.path.join(LOG_DIR, f"{date_str}.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    rows.reverse()
    return rows


def log_file_path(date_str):
    """Returns the on-disk path for a given date's log file, or None if
    the date is invalid or the file doesn't exist. Used for downloads."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    path = os.path.join(LOG_DIR, f"{date_str}.csv")
    return path if os.path.exists(path) else None


def cleanup_old_logs():
    """Deletes log files older than RETENTION_DAYS from today. Only acts on
    files matching the expected YYYY-MM-DD.csv naming pattern."""
    _ensure_log_dir()
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=RETENTION_DAYS)
    for fname in os.listdir(LOG_DIR):
        if not fname.endswith(".csv"):
            continue
        try:
            file_date = datetime.strptime(fname[:-4], "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(os.path.join(LOG_DIR, fname))
                print(f"[event_log] Deleted log file older than {RETENTION_DAYS} days: {fname}")
            except OSError as e:
                print(f"[event_log] Failed to delete {fname}: {e}")


def _cleanup_loop():
    while True:
        cleanup_old_logs()
        time.sleep(24 * 60 * 60)   # once a day is plenty


def start_cleanup_thread():
    threading.Thread(target=_cleanup_loop, daemon=True).start()
