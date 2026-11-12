"""
receipts.py - a tamper-evident record of every case.

Each receipt stores the hash of the receipt before it, like a chain.
If anyone edits an old receipt, its hash no longer matches, and
verify_chain() reports exactly where the chain broke.

Receipts are saved in data/receipts/00001.json, 00002.json, ...
"""
import hashlib
import json
import threading
from datetime import datetime, timezone

from .config import settings

lock = threading.Lock()
FIRST_PREVIOUS_HASH = "GENESIS"   # the first receipt has nothing before it


def receipts_dir():
    return settings.data_dir / "receipts"


def compute_hash(receipt):
    """SHA-256 of everything in the receipt except the hash itself."""
    content = {
        "seq": receipt["seq"],
        "id": receipt["id"],
        "createdAt": receipt["createdAt"],
        "previousHash": receipt["previousHash"],
        "body": receipt["body"],
    }
    text = json.dumps(content, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def load_receipts():
    """All receipts, oldest first."""
    folder = receipts_dir()
    if not folder.exists():
        return []
    receipts = []
    for path in sorted(folder.glob("*.json")):
        receipts.append(json.loads(path.read_text(encoding="utf-8")))
    return receipts


def save_receipt(body):
    """Add a new receipt to the end of the chain and return it."""
    with lock:
        existing = load_receipts()
        if existing:
            previous_hash = existing[-1]["hash"]
        else:
            previous_hash = FIRST_PREVIOUS_HASH
        seq = len(existing) + 1
        receipt = {
            "seq": seq,
            "id": f"CS-{seq:04d}",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "previousHash": previous_hash,
            "body": body,
        }
        receipt["hash"] = compute_hash(receipt)
        receipts_dir().mkdir(parents=True, exist_ok=True)
        path = receipts_dir() / f"{seq:05d}.json"
        path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return receipt


def get_receipt(receipt_id):
    for receipt in load_receipts():
        if receipt["id"] == receipt_id:
            return receipt
    return None


def verify_chain():
    """Re-check every hash and every link. Returns {"ok", "checked", "brokenAt", "problem"}."""
    previous_hash = FIRST_PREVIOUS_HASH
    receipts = load_receipts()
    for receipt in receipts:
        if receipt["previousHash"] != previous_hash:
            return {"ok": False, "checked": len(receipts), "brokenAt": receipt["id"], "problem": "link to the previous receipt does not match"}
        if compute_hash(receipt) != receipt["hash"]:
            return {"ok": False, "checked": len(receipts), "brokenAt": receipt["id"], "problem": "contents were changed after it was saved"}
        previous_hash = receipt["hash"]
    return {"ok": True, "checked": len(receipts), "brokenAt": None, "problem": None}
