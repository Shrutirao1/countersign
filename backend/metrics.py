"""
metrics.py - measure every case: AI calls, tokens, cost and seconds.

This is how we PROVE the speed and cost claims instead of guessing.
Every AI call is recorded here and also appended to data/calls.jsonl.
"""
import json
import statistics
import threading
import time

from .config import settings


def price_per_million(model):
    """Dollars per million tokens (input, output) for a model, from your .env."""
    if model == settings.judge_model:
        return settings.price_judge_in, settings.price_judge_out
    return settings.price_fast_in, settings.price_fast_out


def cost_of(model, input_tokens, output_tokens):
    price_in, price_out = price_per_million(model)
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class CaseMetrics:
    """Collects the numbers for one case (or one evaluation run)."""

    def __init__(self):
        self.started = time.time()
        self.calls = []            # one dict per AI call
        self.offline_steps = 0     # agent steps answered by the offline analyzer
        self.decided_by_code = 0   # offers decided without any AI
        self.cache_hits = 0        # fine print we did not need to read again
        self.lock = threading.Lock()  # agents may finish at the same time

    def record_call(self, agent, model, mode, input_tokens, output_tokens, seconds, fallback_reason=None):
        call = {
            "agent": agent,
            "model": model,
            "mode": mode,                      # "live" or "mock"
            "inputTokens": int(input_tokens),
            "outputTokens": int(output_tokens),
            "seconds": round(seconds, 3),
            "cost": cost_of(model, input_tokens, output_tokens),
            "fellBack": fallback_reason is not None,
            "fallbackReason": fallback_reason,
        }
        with self.lock:
            self.calls.append(call)
        # Keep a permanent log of every call.
        try:
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            with open(settings.data_dir / "calls.jsonl", "a", encoding="utf-8") as log:
                log.write(json.dumps(call) + "\n")
        except OSError:
            pass

    def summary(self):
        """Totals for the whole case, shown under the verdict."""
        by_agent = {}
        for call in self.calls:
            by_agent[call["agent"]] = by_agent.get(call["agent"], 0) + 1
        return {
            "aiCalls": len(self.calls),
            "byAgent": by_agent,
            "inputTokens": sum(call["inputTokens"] for call in self.calls),
            "outputTokens": sum(call["outputTokens"] for call in self.calls),
            "cost": round(sum(call["cost"] for call in self.calls), 6),
            "fallbacks": sum(1 for call in self.calls if call["fellBack"]),
            "offlineSteps": self.offline_steps,
            "decidedByCode": self.decided_by_code,
            "cacheHits": self.cache_hits,
            "seconds": round(time.time() - self.started, 3),
            "pricesSet": settings.price_fast_in > 0 or settings.price_judge_in > 0,
        }


def median(values):
    if not values:
        return 0
    return statistics.median(values)


def percentile_95(values):
    """The value 95% of runs are faster than (the 'slowest 5%' line)."""
    if not values:
        return 0
    ordered = sorted(values)
    index = round(0.95 * (len(ordered) - 1))
    return ordered[index]
