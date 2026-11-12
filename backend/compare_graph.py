"""
compare_graph.py - check that the LangGraph version decides exactly like the original.

    python -m backend.compare_graph

Runs offline (no AI key, no cost, no PayPal) and writes nothing to your data folder:
  1) all 40 labeled evaluation offers through BOTH trial.decide_offer and graph.decide_offer_graph
  2) the 3 demo scenarios end to end with the LangGraph version swapped in
and prints whether every verdict matches.
"""
import tempfile
from pathlib import Path

from backend import trial
from backend.config import settings

# Offline and isolated: no AI, simulated PayPal, a throwaway data folder.
settings.ai_mode = "offline"
settings.paypal_client_id = ""
settings.paypal_client_secret = ""
settings.data_dir = Path(tempfile.mkdtemp(prefix="cx-graph-"))

from backend.catalog import SCENARIOS                       # noqa: E402
from backend.facts_cache import clear_cache                  # noqa: E402
from backend.graph import decide_offer_graph                 # noqa: E402
from backend.metrics import CaseMetrics                      # noqa: E402
from backend.paypal_client import authorize_order, create_mandate_order  # noqa: E402
from backend.precedents import reset_precedents              # noqa: E402
from backend.risk import score_risk                          # noqa: E402
from evals.dataset import OFFERS                             # noqa: E402
from evals.run import EVAL_RULES                             # noqa: E402


def decide_both(item):
    merchant = {"id": f"eval-{item['id']}", "name": "Eval merchant", "caseFile": None}
    context = {"request": f"Buy a {item['title'].lower()}.", "protectedPerson": "the buyer", "rules": EVAL_RULES}
    risk = score_risk(item, merchant, EVAL_RULES)
    answers = []
    for decide in (trial.decide_offer, decide_offer_graph):
        metrics = CaseMetrics()
        events = []
        facts = trial.read_fine_print([item], None, metrics, events.append)[item["id"]]
        outcome = decide(item, merchant, risk, facts, context, events.append, 1, None, metrics)
        answers.append((outcome["verdict"], outcome["decidedBy"], [e["type"] for e in events]))
    return answers


def run_scenarios(decide):
    original = trial.decide_offer
    trial.decide_offer = decide          # run_case looks decide_offer up at call time
    try:
        reset_precedents()
        clear_cache()
        verdicts = []
        for scenario in SCENARIOS:
            rules = scenario["defaultRules"]
            order = create_mandate_order(rules["budget"], "graph check")
            auth = authorize_order(order["id"])
            result = trial.run_case(scenario["id"], rules, auth, lambda event: None, client=None)
            verdicts.append((scenario["id"], [h["verdict"] for h in result["history"]], result["status"]))
        return verdicts
    finally:
        trial.decide_offer = original


def main():
    mismatches = 0
    for item in OFFERS:
        (v1, by1, ev1), (v2, by2, ev2) = decide_both(item)
        same = v1 == v2 and by1 == by2 and ev1 == ev2
        if not same:
            mismatches = mismatches + 1
            print(f"  DIFFERENT  {item['id']}: original {v1}/{by1}  graph {v2}/{by2}")
    print(f"1) 40 labeled offers: {len(OFFERS) - mismatches}/{len(OFFERS)} identical (verdict, decided-by, event order)")

    original = run_scenarios(trial.decide_offer)
    graph = run_scenarios(decide_offer_graph)
    for (sid, v1, s1), (_, v2, s2) in zip(original, graph):
        flag = "same" if (v1, s1) == (v2, s2) else "DIFFERENT"
        print(f"2) {sid:<10} original {v1} {s1}   graph {v2} {s2}   {flag}")
        if flag != "same":
            mismatches = mismatches + 1

    print("\nReady! The LangGraph version decides exactly like the original." if mismatches == 0
          else f"\nNot ready: {mismatches} difference(s). Keep using the original.")


if __name__ == "__main__":
    main()
