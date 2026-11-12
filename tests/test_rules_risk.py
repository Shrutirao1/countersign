"""Rules, risk tiers, case law and the facts cache."""
import pytest

from backend.catalog import OFFERS, STANDARD_RULES, get_merchant
from backend.facts_cache import get_cached_facts, save_facts
from backend.precedents import precedents_for, record_precedent
from backend.risk import score_risk
from backend.rules import check_rules, failed_rules, true_year_cost

NO_EVIDENCE = {"totalDueToday": [], "recurring": [], "returnCost": [], "hiddenFees": []}


def find_offer(offer_id):
    return next(offer for offer in OFFERS if offer["id"] == offer_id)


def make_facts(**changes):
    facts = {"totalDueToday": 10.0, "recurring": None, "returnCost": 0, "hiddenFees": [], "evidence": NO_EVIDENCE}
    facts.update(changes)
    return facts


def test_a_clean_purchase_passes_every_rule():
    assert failed_rules(check_rules(make_facts(), STANDARD_RULES)) == []


def test_subscription_budget_returns_and_fees_all_fail():
    bad = make_facts(totalDueToday=120, recurring={"amount": 79, "interval": "month"}, returnCost=32.3,
                     hiddenFees=[{"label": "Handling fee", "amount": 8.5}])
    assert len(failed_rules(check_rules(bad, STANDARD_RULES))) == 4


def test_true_year_cost_counts_the_renewals():
    facts = make_facts(totalDueToday=4.99, recurring={"amount": 79, "interval": "month"})
    assert true_year_cost(facts) == pytest.approx(952.99)


def test_risk_tiers_for_the_demo_offers():
    tiers = {}
    for offer_id in ("bp-quickcare", "bp-medmart", "bp-pulseright", "bp-carecheck"):
        offer = find_offer(offer_id)
        tiers[offer_id] = score_risk(offer, get_merchant(offer["merchantId"]), STANDARD_RULES)["tier"]
    assert tiers == {"bp-quickcare": "high", "bp-medmart": "medium", "bp-pulseright": "medium", "bp-carecheck": "low"}


def test_case_law_raises_a_repeat_offender_to_high():
    offer = find_offer("bp-medmart")
    record_precedent({"merchantId": "medmart", "offerId": offer["id"], "issues": ["hidden fees"]})
    assert len(precedents_for("medmart")) == 1
    assert score_risk(offer, get_merchant("medmart"), STANDARD_RULES)["tier"] == "high"


def test_cache_returns_facts_only_for_the_same_text():
    offer = find_offer("bp-medmart")
    save_facts(offer, make_facts(totalDueToday=55.48))
    assert get_cached_facts(offer)["totalDueToday"] == 55.48
    changed = dict(offer, evidence=offer["evidence"][:2])      # merchant changed its terms
    assert get_cached_facts(changed) is None
