"""The LangGraph version must decide every labeled offer exactly like the original.
Skipped automatically when langgraph is not installed, so the main test suite is unchanged."""
import pytest

pytest.importorskip("langgraph")

from backend import trial                                    # noqa: E402
from backend.graph import decide_offer_graph                 # noqa: E402
from backend.metrics import CaseMetrics                      # noqa: E402
from backend.risk import score_risk                          # noqa: E402
from evals.dataset import OFFERS                             # noqa: E402
from evals.run import EVAL_RULES                             # noqa: E402


@pytest.mark.parametrize("item", OFFERS, ids=[o["id"] for o in OFFERS])
def test_graph_matches_original(item):
    merchant = {"id": f"eval-{item['id']}", "name": "Eval merchant", "caseFile": None}
    context = {"request": "Buy it.", "protectedPerson": "the buyer", "rules": EVAL_RULES}
    risk = score_risk(item, merchant, EVAL_RULES)
    outcomes = []
    for decide in (trial.decide_offer, decide_offer_graph):
        metrics = CaseMetrics()
        facts = trial.read_fine_print([item], None, metrics, lambda e: None)[item["id"]]
        outcome = decide(item, merchant, risk, facts, context, lambda e: None, 1, None, metrics)
        outcomes.append((outcome["verdict"], outcome["decidedBy"]))
    assert outcomes[0] == outcomes[1]
