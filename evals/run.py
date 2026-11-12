"""
run.py - score the agents on the 40 labeled offers.

Examples:
    python -m evals.run --config offline --split dev
    python -m evals.run --config small --split dev --repeats 3     (needs ANTHROPIC_API_KEY)
    python -m evals.run --config mixed --split test --repeats 3    (run ONCE, after the freeze)

Configurations:
    offline -> no AI, pattern matching only (the baseline)
    mock    -> offline answers with a fake delay (checks the harness without a key)
    small   -> real AI, the small fast model for every agent
    large   -> real AI, the large model for every agent
    mixed   -> real AI, small model to read, large model to judge (the shipped design)

Writes evals/results/<config>-<split>.json and rebuilds evals/report.md.
"""
import argparse
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.llm import make_client
from backend.metrics import CaseMetrics, median, percentile_95
from backend.risk import score_risk
from backend.rules import hidden_total
from backend.trial import decide_offer, read_fine_print

from .dataset import EVAL_RULES, offers_in
from .report import RESULTS, write_report


def set_up(config):
    """Change the settings for this evaluation run."""
    # Evaluate the model itself: no cache, no case law, and keep test data out of your demo data.
    settings.use_cache = False
    settings.use_case_law = False
    settings.data_dir = Path(tempfile.mkdtemp(prefix="cx-eval-"))

    if config == "offline":
        settings.ai_mode = "offline"
        return
    if config == "mock":
        settings.ai_mode = "mock"
        return
    if not settings.anthropic_api_key:
        raise SystemExit(f"The '{config}' configuration uses the real AI. Put ANTHROPIC_API_KEY in your .env file first.")
    settings.ai_mode = "live"
    small = settings.fast_model
    large = settings.judge_model
    if config == "small":
        settings.fast_model = small
        settings.judge_model = small
    elif config == "large":
        settings.fast_model = large
        settings.judge_model = large
    # "mixed" keeps the normal settings: small to read, large to judge.


def numbers_match(a, b, tolerance=0.05):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tolerance


def recurring_match(found, expected):
    if found is None or expected is None:
        return found is None and expected is None
    return numbers_match(found["amount"], expected["amount"]) and found["interval"] == expected["interval"]


def evaluate_offer(item, client):
    """Run one labeled offer through the real decision code and score it."""
    metrics = CaseMetrics()
    merchant = {"id": f"eval-{item['id']}", "name": "Eval merchant", "caseFile": None}
    context = {"request": f"Buy a {item['title'].lower()}.", "protectedPerson": "the buyer", "rules": EVAL_RULES}
    events = []

    start = time.time()
    risk = score_risk(item, merchant, EVAL_RULES)
    facts = read_fine_print([item], client, metrics, events.append)[item["id"]]
    outcome = decide_offer(item, merchant, risk, facts, context, events.append, 1, client, metrics)
    seconds = time.time() - start

    expected = item["expected"]
    checks = {
        "total": numbers_match(facts["totalDueToday"], expected["totalDueToday"], 0.01),
        "recurring": recurring_match(facts.get("recurring"), expected["recurring"]),
        "returnCost": numbers_match(facts.get("returnCost"), expected["returnCost"]),
        "hiddenFees": numbers_match(hidden_total(facts), expected["hiddenFeeTotal"], 0.01),
    }
    dropped = sum(event.get("dropped", 0) for event in events if event["type"] == "argument")
    summary = metrics.summary()
    return {
        "id": item["id"], "group": item["group"], "title": item["title"],
        "expected": expected["verdict"], "got": outcome["verdict"], "correct": outcome["verdict"] == expected["verdict"],
        "decidedBy": outcome["decidedBy"], "tier": risk["tier"],
        "fieldChecks": checks, "fieldsCorrect": sum(1 for ok in checks.values() if ok),
        "found": {"totalDueToday": facts["totalDueToday"], "recurring": facts.get("recurring"),
                  "returnCost": facts.get("returnCost"), "hiddenFees": hidden_total(facts)},
        "seconds": round(seconds, 3), "aiCalls": summary["aiCalls"], "fallbacks": summary["fallbacks"],
        "inputTokens": summary["inputTokens"], "outputTokens": summary["outputTokens"], "cost": summary["cost"],
        "droppedCitations": dropped, "safetyNet": facts.get("safetyNet", []), "reason": expected["reason"],
    }


def summarize(rows, repeats):
    offer_ids = sorted(set(row["id"] for row in rows))
    false_approvals = sorted(set(row["id"] for row in rows if row["expected"] == "REJECT" and row["got"] == "APPROVE"))
    false_rejections = sorted(set(row["id"] for row in rows if row["expected"] == "APPROVE" and row["got"] == "REJECT"))
    ai_calls = sum(row["aiCalls"] for row in rows)
    fallbacks = sum(row["fallbacks"] for row in rows)
    seconds = [row["seconds"] for row in rows]

    # Consistency: did every repeat of an offer give the same verdict?
    consistency = None
    if repeats > 1:
        same = 0
        for offer_id in offer_ids:
            verdicts = set(row["got"] for row in rows if row["id"] == offer_id)
            if len(verdicts) == 1:
                same = same + 1
        consistency = same / len(offer_ids)

    by_group = {}
    for row in rows:
        group = by_group.setdefault(row["group"], {"runs": 0, "correct": 0})
        group["runs"] = group["runs"] + 1
        if row["correct"]:
            group["correct"] = group["correct"] + 1

    fallback_rate = None
    if ai_calls:
        fallback_rate = fallbacks / ai_calls
    field_accuracy = sum(row["fieldsCorrect"] for row in rows) / (4 * len(rows))

    bars = [
        {"metric": "Traps approved", "value": len(false_approvals), "bar": "0", "passed": len(false_approvals) == 0},
        {"metric": "Good offers blocked", "value": len(false_rejections), "bar": "2 or fewer", "passed": len(false_rejections) <= 2},
        {"metric": "Field accuracy", "value": round(field_accuracy, 3), "bar": "90% or better", "passed": field_accuracy >= 0.90},
        {"metric": "Fallback rate", "value": fallback_rate, "bar": "under 5%", "passed": None if fallback_rate is None else fallback_rate < 0.05},
        {"metric": "Median seconds", "value": round(median(seconds), 3), "bar": "under 10 s", "passed": median(seconds) < 10},
        {"metric": "Consistency", "value": consistency, "bar": "95% or better", "passed": None if consistency is None else consistency >= 0.95},
    ]
    return {
        "offers": len(offer_ids), "runs": len(rows),
        "accuracy": sum(1 for row in rows if row["correct"]) / len(rows),
        "falseApprovals": false_approvals, "falseRejections": false_rejections,
        "fieldAccuracy": field_accuracy, "droppedCitations": sum(row["droppedCitations"] for row in rows),
        "aiCalls": ai_calls, "fallbackRate": fallback_rate,
        "medianSeconds": median(seconds), "p95Seconds": percentile_95(seconds),
        "avgAiCalls": ai_calls / len(rows), "avgCost": sum(row["cost"] for row in rows) / len(rows),
        "avgInputTokens": sum(row["inputTokens"] for row in rows) / len(rows),
        "consistency": consistency, "byGroup": by_group, "bars": bars,
        "safetyNetCatches": sum(1 for row in rows if row["safetyNet"]),
    }


def run(config, split, repeats):
    set_up(config)
    client = make_client()
    rows = []
    for item in offers_in(split):
        for repeat in range(repeats):
            rows.append(evaluate_offer(item, client))
    summary = summarize(rows, repeats)
    result = {
        "config": config, "split": split, "repeats": repeats, "aiMode": settings.llm_mode,
        "models": {"fast": settings.fast_model, "judge": settings.judge_model},
        "createdAt": datetime.now(timezone.utc).isoformat(), "summary": summary, "rows": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{config}-{split}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_report()
    return result


def print_result(result):
    s = result["summary"]
    print(f"\nConfiguration: {result['config']}   split: {result['split']}   offers: {s['offers']} x {result['repeats']}")
    print(f"Accuracy {s['accuracy'] * 100:.0f}%   field accuracy {s['fieldAccuracy'] * 100:.0f}%   "
          f"median {s['medianSeconds']:.2f} s   AI calls/offer {s['avgAiCalls']:.1f}   cost/offer ${s['avgCost']:.4f}")
    for bar in s["bars"]:
        if bar["passed"] is None:
            mark = "n/a "
        elif bar["passed"]:
            mark = "PASS"
        else:
            mark = "FAIL"
        print(f"  {mark}  {bar['metric']:<20} {bar['value']}   (bar: {bar['bar']})")
    print(f"  Traps approved: {', '.join(s['falseApprovals']) or 'none'}")
    print(f"  Good offers blocked: {', '.join(s['falseRejections']) or 'none'}")
    print("Wrote evals/results and evals/report.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score Countersign on labeled offers.")
    parser.add_argument("--config", default="offline", choices=["offline", "mock", "small", "large", "mixed"])
    parser.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    print_result(run(args.config, args.split, args.repeats))
