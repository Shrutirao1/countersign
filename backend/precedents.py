"""
precedents.py - "case law".

Every rejection is remembered per merchant in data/precedents.json.
A merchant caught once starts its next case at a higher risk.
"""
import json
import threading
from datetime import datetime, timezone

from .config import settings

# A lock stops two cases from writing the file at the same moment.
lock = threading.Lock()


def precedents_file():
    return settings.data_dir / "precedents.json"


def load_all():
    """Read every precedent. An empty or missing file means no case law yet."""
    try:
        return json.loads(precedents_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_all(items):
    precedents_file().parent.mkdir(parents=True, exist_ok=True)
    precedents_file().write_text(json.dumps(items, indent=2), encoding="utf-8")


def precedents_for(merchant_id):
    """All past rejections for one merchant."""
    if not settings.use_case_law:
        return []
    return [item for item in load_all() if item["merchantId"] == merchant_id]


def all_precedents():
    return load_all()


def record_precedent(entry):
    """Remember a rejection."""
    if not settings.use_case_law:
        return
    with lock:
        items = load_all()
        entry["date"] = datetime.now(timezone.utc).isoformat()
        items.append(entry)
        save_all(items)


def reset_precedents():
    with lock:
        save_all([])
