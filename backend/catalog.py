"""
catalog.py - the fake stores for the demo.

We build our own fake merchants so the demo is reliable and the traps are
exactly where we want them. Each offer has:

  displayPrice -> the price shown on the product page
  declared     -> what the checkout claims (all a naive shopping agent sees)
  evidence     -> the real text of the product page, checkout and fine print,
                  split into lines E1, E2, ... Every agent must cite these IDs.

A merchant with a verified "caseFile" has submitted honest terms up front.
It gets the Trial-Tested fast lane: approved by code, no AI needed.

Run this file to list everything:   python -m backend.catalog
"""


def evidence(*lines):
    """Turn (source, text) pairs into evidence lines with IDs E1, E2, ..."""
    result = []
    number = 1
    for source, text in lines:
        result.append({"id": f"E{number}", "source": source, "text": text})
        number = number + 1
    return result


# ---------------------------------------------------------------
# Merchants
# ---------------------------------------------------------------
MERCHANTS = {
    "quickcare": {"id": "quickcare", "name": "QuickCare Direct", "caseFile": None},
    "medmart": {"id": "medmart", "name": "MedMart Online", "caseFile": None},
    "pulseright": {"id": "pulseright", "name": "PulseRight Renewed", "caseFile": None},
    "carecheck": {
        "id": "carecheck",
        "name": "CareCheck Health",
        "caseFile": {
            "verified": True,
            "verifiedOn": "2026-10-20",
            "facts": {"totalDueToday": 52.0, "recurring": None, "returnCost": 0, "hiddenFees": []},
        },
    },
    "homebasics": {
        "id": "homebasics",
        "name": "HomeBasics",
        "caseFile": {
            "verified": True,
            "verifiedOn": "2026-09-02",
            "facts": {"totalDueToday": 7.49, "recurring": None, "returnCost": 0, "hiddenFees": []},
        },
    },
    "boxly": {"id": "boxly", "name": "Boxly Meals", "caseFile": None},
    "freshfork": {"id": "freshfork", "name": "FreshFork", "caseFile": None},
}


# ---------------------------------------------------------------
# Offers
# ---------------------------------------------------------------
OFFERS = [
    # ===== Scenario 1: Dad's blood pressure monitor =====
    # Trap 1: a $4.99 "trial" that becomes $79 a month. Code rejects it (no subscriptions).
    {
        "id": "bp-quickcare", "scenario": "dad_bp", "merchantId": "quickcare",
        "title": "VitalTrack Pro Blood Pressure Monitor", "category": "blood pressure monitor",
        "displayPrice": 4.99, "declared": {"totalDueToday": 4.99},
        "evidence": evidence(
            ("Product page", "VitalTrack Pro Blood Pressure Monitor. Start today for just $4.99!"),
            ("Product page", "FREE returns, no questions asked."),
            ("Checkout", "Order total today: $4.99"),
            ("Terms of Service, section 3", "Your $4.99 trial includes 14 days of VitalTrack Premium Membership. After the trial, membership renews automatically at $79.00 per month until cancelled."),
            ("Return Policy, section 2", "Returned devices are subject to a 15% restocking fee of the device's retail value ($129.00). Customer is responsible for return shipping ($12.95 flat rate)."),
            ("Terms of Service, section 7", "Cancellation requests must be submitted by phone during business hours (Mon-Fri, 9am-4pm ET)."),
        ),
    },
    # Trap 2: $39.99 on the product page, $55.48 at checkout. Code rejects it (hidden fees).
    {
        "id": "bp-medmart", "scenario": "dad_bp", "merchantId": "medmart",
        "title": "ArmSense BP5 Upper Arm Monitor", "category": "blood pressure monitor",
        "displayPrice": 39.99, "declared": {"totalDueToday": 39.99},
        "evidence": evidence(
            ("Product page", "ArmSense BP5 Upper Arm Monitor, clinically validated. Only $39.99."),
            ("Checkout", "Subtotal $39.99. Handling & processing fee $8.50. Shipping $6.99. Total $55.48"),
            ("Return Policy", "Free returns within 30 days of delivery."),
        ),
    },
    # Gray area: every rule passes, but a claim is not supported. This one goes to trial.
    {
        "id": "bp-pulseright", "scenario": "dad_bp", "merchantId": "pulseright",
        "title": "PulseRight Refurbished Arm Monitor", "category": "blood pressure monitor",
        "displayPrice": 44.0, "declared": {"totalDueToday": 44.0},
        "evidence": evidence(
            ("Product page", "PulseRight Refurbished Arm Monitor. Clinically validated accuracy. $44.00."),
            ("Checkout", "Total $44.00 (free shipping)."),
            ("Return Policy", "Free returns within 30 days. We pay return shipping."),
            ("Product details", "Refurbished unit. Not intended for medical diagnosis. Clinical validation refers to the original model, before refurbishment."),
        ),
    },
    # Honest merchant with a verified case file: approved instantly, no AI.
    {
        "id": "bp-carecheck", "scenario": "dad_bp", "merchantId": "carecheck",
        "title": "CareCheck Classic Blood Pressure Monitor", "category": "blood pressure monitor",
        "displayPrice": 52.0, "declared": {"totalDueToday": 52.0},
        "evidence": evidence(
            ("Product page", "CareCheck Classic Blood Pressure Monitor. $52.00 including shipping."),
            ("Checkout", "Total $52.00 (shipping included, no other fees)."),
            ("Return Policy", "Free returns within 60 days. We pay return shipping."),
        ),
    },

    # ===== Scenario 2: AA batteries (low risk, approved instantly) =====
    {
        "id": "aa-homebasics", "scenario": "batteries", "merchantId": "homebasics",
        "title": "AA Alkaline Batteries, 12-pack", "category": "batteries",
        "displayPrice": 7.49, "declared": {"totalDueToday": 7.49},
        "evidence": evidence(
            ("Product page", "AA Alkaline Batteries, 12-pack. $7.49."),
            ("Checkout", "Total $7.49"),
            ("Return Policy", "Free returns within 30 days."),
        ),
    },

    # ===== Scenario 3: dinner delivery (every option is a trap, so PayPal voids the hold) =====
    {
        "id": "meal-boxly", "scenario": "mealkit", "merchantId": "boxly",
        "title": "Boxly Dinner Box (first box)", "category": "meal delivery",
        "displayPrice": 1.0, "declared": {"totalDueToday": 1.0},
        "evidence": evidence(
            ("Product page", "Try your first dinner box for just $1!"),
            ("Checkout", "Order total today: $1.00"),
            ("Terms", "After your first box, your plan renews automatically at $69.99 per week until cancelled."),
            ("Terms", "Cancellations take effect after the next scheduled delivery."),
        ),
    },
    {
        "id": "meal-freshfork", "scenario": "mealkit", "merchantId": "freshfork",
        "title": "FreshFork Meal Plan, 50% off first month", "category": "meal delivery",
        "displayPrice": 29.99, "declared": {"totalDueToday": 29.99},
        "evidence": evidence(
            ("Product page", "Half off your first month: $29.99. No commitment!"),
            ("Checkout", "Order total today: $29.99"),
            ("Terms", "Introductory pricing applies to the first month only. Plan renews automatically at $59.99 per month. Early cancellation fee: $25.00."),
        ),
    },
]


# ---------------------------------------------------------------
# Scenarios: the tasks you can give the shopping agent in the demo
# ---------------------------------------------------------------
STANDARD_RULES = {"budget": 100, "noSubscriptions": True, "maxMonthly": 0, "requireFreeReturns": True, "noHiddenFees": True}

SCENARIOS = [
    {
        "id": "dad_bp", "label": "Dad's blood pressure monitor",
        "request": "Buy my dad a blood pressure monitor.", "protectedPerson": "Dad",
        "defaultRules": STANDARD_RULES,
    },
    {
        "id": "batteries", "label": "Reorder AA batteries",
        "request": "Reorder AA batteries for the TV remote.", "protectedPerson": "Dad",
        "defaultRules": {"budget": 20, "noSubscriptions": True, "maxMonthly": 0, "requireFreeReturns": False, "noHiddenFees": True},
    },
    {
        "id": "mealkit", "label": "Cheap dinner delivery",
        "request": "Find Dad a cheap dinner delivery deal.", "protectedPerson": "Dad",
        "defaultRules": {"budget": 50, "noSubscriptions": True, "maxMonthly": 0, "requireFreeReturns": False, "noHiddenFees": True},
    },
]


def get_scenario(scenario_id):
    """Find a scenario by its id. Returns None if there is no such scenario."""
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    return None


def offers_for(scenario_id):
    """All offers the shopping agent can find for a scenario."""
    return [offer for offer in OFFERS if offer["scenario"] == scenario_id]


def get_merchant(merchant_id):
    return MERCHANTS[merchant_id]


# Run "python -m backend.catalog" to print the demo world.
if __name__ == "__main__":
    for scenario in SCENARIOS:
        print(f"{scenario['id']}: {scenario['request']}")
        for offer in offers_for(scenario["id"]):
            merchant = get_merchant(offer["merchantId"])
            tested = ""
            if merchant["caseFile"]:
                tested = "  [Trial-Tested]"
            print(f"    {offer['id']:<16} ${offer['displayPrice']:>6.2f}  {merchant['name']}{tested}")
