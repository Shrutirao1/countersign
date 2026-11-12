"""
facts_cache.py - remember what the AI read from each offer's fine print.

The key is a fingerprint (a hash) of the offer's text. If the merchant changes
even one word of its terms, the fingerprint changes and the AI reads it again.
Same terms -> no AI call -> no cost and no waiting.
"""
import hashlib
import json
import threading

from .config import settings

lock = threading.Lock()


def cache_file():
    return settings.data_dir / "facts_cache.json"


def fingerprint(offer):
    """A short hash of everything the fine-print reader looks at."""
    text = str(offer["displayPrice"]) + "\n"
    for line in offer["evidence"]:
        text = text + line["id"] + "|" + line["source"] + "|" + line["text"] + "\n"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def load_cache():
    try:
        return json.loads(cache_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_cached_facts(offer):
    """Return saved facts for this exact offer text, or None."""
    if not settings.use_cache:
        return None
    return load_cache().get(fingerprint(offer))


def save_facts(offer, facts):
    """Save facts that came from the AI (live or mock), not from a fallback."""
    if not settings.use_cache:
        return
    keep = {
        "totalDueToday": facts["totalDueToday"],
        "recurring": facts.get("recurring"),
        "returnCost": facts.get("returnCost"),
        "hiddenFees": facts.get("hiddenFees", []),
        "evidence": facts.get("evidence", {}),
        "safetyNet": facts.get("safetyNet", []),
    }
    with lock:
        cache = load_cache()
        cache[fingerprint(offer)] = keep
        cache_file().parent.mkdir(parents=True, exist_ok=True)
        cache_file().write_text(json.dumps(cache, indent=2), encoding="utf-8")


def clear_cache():
    with lock:
        cache_file().parent.mkdir(parents=True, exist_ok=True)
        cache_file().write_text("{}", encoding="utf-8")
