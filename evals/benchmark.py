"""
benchmark.py - prove the speed and cost changes: old design vs new design.

    python -m evals.benchmark            (mock AI: fake delay per call, no key needed)
    python -m evals.benchmark --live     (the real AI, needs ANTHROPIC_API_KEY)

Runs the three demo scenarios twice each (a first run, then a repeat run that
can use the cache) with:
    old design -> AI shopper, a trial even after a rule fails, one call at a time, no cache
    new design -> code shopper, rule failure decides, parallel calls, fact cache
and counts AI calls and seconds. Same verdicts, fewer calls, less waiting.

Writes evals/results/benchmark.json and rebuilds evals/report.md.
"""
import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from backend.catalog import SCENARIOS
from backend.config import settings
from backend.facts_cache import clear_cache
from backend.llm import make_client
from backend.paypal_client import authorize_order, create_mandate_order
from backend.precedents import reset_precedents
from backend.trial import run_case

from .report import RESULTS, write_report

DESIGNS = {
    "old": {"use_cache": False, "parallel": False, "skip_trial_on_rule_fail": False, "shopper_uses_ai": True},
    "new": {"use_cache": True, "parallel": True, "skip_trial_on_rule_fail": True, "shopper_uses_ai": False},
}


def run_scenario(scenario):
    rules = scenario["defaultRules"]
    order = create_mandate_order(rules["budget"], "benchmark")
    authorization = authorize_order(order["id"])
    result = run_case(scenario["id"], rules, authorization, lambda event: None, client=make_client())
    return {
        "aiCalls": result["metrics"]["aiCalls"],
        "seconds": result["metrics"]["seconds"],
        "byAgent": result["metrics"]["byAgent"],
        "verdicts": [item["verdict"] for item in result["history"]],
        "outcome": result["status"],
    }


def main(live):
    if live:
        if not settings.anthropic_api_key:
            raise SystemExit("--live needs ANTHROPIC_API_KEY in your .env file.")
        settings.ai_mode = "live"
        note = "Real AI calls."
    else:
        settings.ai_mode = "mock"
        note = f"Mock AI: every call waits {settings.mock_latency_s} s, so seconds show the effect of running calls in parallel. Real seconds come from --live."

    # Keep benchmark receipts and cache out of your demo data.
    settings.data_dir = Path(tempfile.mkdtemp(prefix="cx-bench-"))
    settings.use_case_law = True

    results = {}
    for design, flags in DESIGNS.items():
        for name, value in flags.items():
            setattr(settings, name, value)
        for scenario in SCENARIOS:
            reset_precedents()
            clear_cache()
            first = run_scenario(scenario)
            reset_precedents()          # same starting point; only the cache is kept
            repeat = run_scenario(scenario)
            results[(design, scenario["id"], "first run")] = first
            results[(design, scenario["id"], "repeat run")] = repeat
            print(f"{design} design  {scenario['label']:<30} first: {first['aiCalls']:>2} calls {first['seconds']:.2f} s   "
                  f"repeat: {repeat['aiCalls']:>2} calls {repeat['seconds']:.2f} s   verdicts {first['verdicts']}")

    comparison = []
    for scenario in SCENARIOS:
        for run_name in ("first run", "repeat run"):
            old = results[("old", scenario["id"], run_name)]
            new = results[("new", scenario["id"], run_name)]
            comparison.append({
                "scenario": scenario["label"], "run": run_name,
                "oldCalls": old["aiCalls"], "oldSeconds": old["seconds"],
                "newCalls": new["aiCalls"], "newSeconds": new["seconds"],
                "sameVerdicts": old["verdicts"] == new["verdicts"],
            })

    output = {"aiMode": settings.llm_mode, "note": note, "createdAt": datetime.now(timezone.utc).isoformat(), "comparison": comparison}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "benchmark.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    write_report()
    all_same = all(row["sameVerdicts"] for row in comparison)
    print(f"\nSame verdicts in both designs: {all_same}")
    print("Wrote evals/results/benchmark.json and evals/report.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Old design vs new design.")
    parser.add_argument("--live", action="store_true", help="use the real AI instead of mock")
    main(parser.parse_args().live)

