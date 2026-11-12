"""Checks on the demo data."""
from backend.catalog import MERCHANTS, OFFERS, SCENARIOS, offers_for


def test_every_offer_has_a_known_merchant_and_scenario():
    scenario_ids = [scenario["id"] for scenario in SCENARIOS]
    for offer in OFFERS:
        assert offer["merchantId"] in MERCHANTS
        assert offer["scenario"] in scenario_ids


def test_evidence_ids_are_unique_inside_each_offer():
    for offer in OFFERS:
        ids = [line["id"] for line in offer["evidence"]]
        assert len(ids) == len(set(ids)), offer["id"]


def test_every_scenario_has_offers():
    for scenario in SCENARIOS:
        assert len(offers_for(scenario["id"])) > 0


def test_the_trap_is_hidden_in_the_fine_print():
    trap = next(offer for offer in OFFERS if offer["id"] == "bp-quickcare")
    assert trap["declared"]["totalDueToday"] == 4.99     # what a naive agent sees
    assert any("renews automatically" in line["text"] for line in trap["evidence"])
