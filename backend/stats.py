"""
stats.py - totals for the Dashboard tab, added up from the saved receipts.
"""
from .receipts import load_receipts


def dashboard_stats():
    receipts = load_receipts()
    cases = len(receipts)
    approved_spend = 0.0
    blocked = 0.0
    ai_calls = 0
    seconds = 0.0
    offers_total = 0
    offers_by_code = 0
    trials = 0
    recent = []

    for receipt in receipts:
        body = receipt["body"]
        approved_spend = approved_spend + body["payment"]["amount"]
        blocked = blocked + body["counterfactual"]["saved"]
        ai_calls = ai_calls + body["metrics"]["aiCalls"]
        seconds = seconds + body["metrics"]["seconds"]
        for offer in body["offers"]:
            offers_total = offers_total + 1
            if offer["decidedBy"] == "code":
                offers_by_code = offers_by_code + 1
            if offer["decidedBy"] == "trial":
                trials = trials + 1
        recent.append({
            "id": receipt["id"],
            "createdAt": receipt["createdAt"],
            "request": body["request"],
            "outcome": body["outcome"],
            "amount": body["payment"]["amount"],
            "saved": body["counterfactual"]["saved"],
            "aiCalls": body["metrics"]["aiCalls"],
            "seconds": body["metrics"]["seconds"],
            "aiMode": body["aiMode"],
        })

    def average(total):
        if cases == 0:
            return 0
        return round(total / cases, 2)

    share_by_code = 0
    if offers_total:
        share_by_code = round(100 * offers_by_code / offers_total)

    return {
        "cases": cases,
        "approvedSpend": round(approved_spend, 2),
        "blockedFirstYear": round(blocked, 2),
        "avgAiCalls": average(ai_calls),
        "avgSeconds": average(seconds),
        "offersChecked": offers_total,
        "decidedByCodePercent": share_by_code,
        "trials": trials,
        "recent": list(reversed(recent))[:15],   # newest first
    }
