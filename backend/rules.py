"""
rules.py - the guardian's hard rules, checked by plain code.

The AI agents can argue, but they can never talk their way past these.
If any rule fails, the purchase is rejected, whatever the judge thinks.
"""


def check_rules(facts, rules):
    """
    Check the facts of one offer against the guardian's rules.

    facts -> totalDueToday, recurring, returnCost, hiddenFees, evidence
    rules -> budget, noSubscriptions, maxMonthly, requireFreeReturns, noHiddenFees

    Returns a list like [{"rule": ..., "passed": True/False, "detail": ..., "evidence": [...]}]
    """
    results = []
    evidence = facts.get("evidence") or {}
    total = facts["totalDueToday"]
    recurring = facts.get("recurring")

    # Rule 1: the amount due today must fit the budget.
    results.append({
        "rule": f"Total today must be at most ${rules['budget']:g}",
        "passed": total <= rules["budget"] + 0.001,
        "detail": f"Total due today is ${total:.2f}",
        "evidence": evidence.get("totalDueToday", []),
    })

    # Rule 2: no subscriptions (or, if subscriptions are allowed, a monthly cap).
    if rules["noSubscriptions"]:
        if recurring:
            detail = f"Renews at ${recurring['amount']:.2f} per {recurring['interval']}"
        else:
            detail = "No recurring charge found"
        results.append({
            "rule": "No subscriptions or auto-renewals",
            "passed": recurring is None,
            "detail": detail,
            "evidence": evidence.get("recurring", []),
        })
    elif rules["maxMonthly"] > 0 and recurring:
        monthly = to_monthly(recurring)
        results.append({
            "rule": f"Recurring charges at most ${rules['maxMonthly']:g}/month",
            "passed": monthly <= rules["maxMonthly"] + 0.001,
            "detail": f"About ${monthly:.2f} per month",
            "evidence": evidence.get("recurring", []),
        })

    # Rule 3: returns must be free.
    if rules["requireFreeReturns"]:
        cost = facts.get("returnCost")
        if cost is None:
            detail = "Return terms not found"
        elif cost == 0:
            detail = "Returns are free"
        else:
            detail = f"Returning it costs about ${cost:.2f}"
        results.append({
            "rule": "Returns must be free",
            "passed": cost == 0,
            "detail": detail,
            "evidence": evidence.get("returnCost", []),
        })

    # Rule 4: no fees beyond the advertised price.
    if rules["noHiddenFees"]:
        hidden = facts.get("hiddenFees") or []
        if hidden:
            parts = [f"{fee['label']} ${fee['amount']:.2f}" for fee in hidden]
            detail = ", ".join(parts) + f" (+${hidden_total(facts):.2f})"
        else:
            detail = "Advertised price matches the total"
        results.append({
            "rule": "No fees beyond the advertised price",
            "passed": len(hidden) == 0,
            "detail": detail,
            "evidence": evidence.get("hiddenFees", []),
        })

    return results


def failed_rules(results):
    """Only the rules that failed."""
    return [result for result in results if not result["passed"]]


def hidden_total(facts):
    """Add up all hidden fees."""
    total = 0.0
    for fee in facts.get("hiddenFees") or []:
        total = total + fee["amount"]
    return round(total, 2)


def to_monthly(recurring):
    """Turn a weekly or yearly charge into a monthly amount."""
    if recurring["interval"] == "week":
        return recurring["amount"] * 52 / 12
    if recurring["interval"] == "year":
        return recurring["amount"] / 12
    return recurring["amount"]


def true_year_cost(facts):
    """What the purchase really costs in its first year (today + 12 months of renewals)."""
    if not facts.get("recurring"):
        return facts["totalDueToday"]
    return facts["totalDueToday"] + to_monthly(facts["recurring"]) * 12
