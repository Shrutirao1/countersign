"""
The whole case, end to end, with simulated PayPal.
These tests PROVE the plan's numbers: verdicts, AI calls, the cache, and the old-vs-new design.
"""
from backend.catalog import get_scenario
from backend.config import settings
from backend.facts_cache import clear_cache
from backend.llm import MockClient
from backend.paypal_client import SIM, authorize_order, create_mandate_order
from backend.precedents import reset_precedents
from backend.trial import run_case

OLD_DESIGN = {"use_cache": False, "parallel": False, "skip_trial_on_rule_fail": False, "shopper_uses_ai": True}


def run(scenario_id, client=None, **rule_changes):
    rules = dict(get_scenario(scenario_id)["defaultRules"])
    rules.update(rule_changes)
    auth = authorize_order(create_mandate_order(rules["budget"], "test")["id"])
    events = []
    result = run_case(scenario_id, rules, auth, events.append, client=client)
    return result, events, auth


def of_type(events, kind):
    return [event for event in events if event["type"] == kind]


def test_dad_case_traps_rejected_by_code_gray_area_tried_then_52_captured():
    result, events, auth = run("dad_bp")
    decided = [(item["merchant"], item["verdict"], item["decidedBy"]) for item in result["history"]]
    assert decided == [
        ("QuickCare Direct", "REJECT", "code"),       # $79/month renewal
        ("MedMart Online", "REJECT", "code"),         # hidden fees
        ("PulseRight Renewed", "REJECT", "trial"),    # unsupported claim, needs judgment
        ("CareCheck Health", "APPROVE", "code"),      # verified merchant
    ]
    payment = of_type(events, "payment")[0]
    assert (payment["action"], payment["amount"], payment["released"]) == ("capture", 52.0, 48.0)
    assert SIM[auth["authorizationId"]]["status"] == "CAPTURED"


def test_counterfactual_shows_what_the_naive_agent_would_pay():
    result, events, auth = run("dad_bp")
    assert result["counterfactual"]["naiveYearCost"] == 952.99
    assert result["counterfactual"]["saved"] == 900.99


def test_meal_kit_voids_the_hold_and_batteries_need_no_ai():
    result, events, auth = run("mealkit")
    assert result["status"] == "voided" and SIM[auth["authorizationId"]]["status"] == "VOIDED"
    result, events, auth = run("batteries")
    assert result["status"] == "approved" and not of_type(events, "argument")


def test_new_design_ai_calls_match_the_plan():
    """Mock AI counts calls exactly like the real AI would."""
    settings.mock_latency_s = 0.01
    expected = {"dad_bp": 6, "batteries": 0, "mealkit": 2}
    for scenario_id, calls in expected.items():
        reset_precedents()
        clear_cache()
        result, events, auth = run(scenario_id, MockClient())
        assert result["metrics"]["aiCalls"] == calls, scenario_id


def test_cache_halves_the_repeat_dad_case():
    settings.mock_latency_s = 0.01
    run("dad_bp", MockClient())
    reset_precedents()
    result, events, auth = run("dad_bp", MockClient())
    assert result["metrics"]["aiCalls"] == 3 and result["metrics"]["cacheHits"] == 3


def test_old_design_makes_14_calls_with_the_same_verdicts():
    settings.mock_latency_s = 0.01
    new_result, events, auth = run("dad_bp", MockClient())
    for name, value in OLD_DESIGN.items():
        setattr(settings, name, value)
    reset_precedents()
    old_result, events, auth = run("dad_bp", MockClient())
    assert old_result["metrics"]["aiCalls"] == 14
    assert [item["verdict"] for item in old_result["history"]] == [item["verdict"] for item in new_result["history"]]


def test_case_ends_with_metrics_and_a_receipt():
    result, events, auth = run("dad_bp")
    types = [event["type"] for event in events]
    assert types[-4:] == ["counterfactual", "metrics", "summary", "receipt"]
    assert result["receipt"]["id"] == "CS-0001"
