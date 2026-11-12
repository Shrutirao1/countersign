"""
risk.py - an instant risk score for each offer, in plain code (no AI).

The score decides how much checking an offer gets:
    low    (10 or less) -> verified merchant: approved by code, no AI
    medium (11 to 40)   -> read the fine print, one quick AI check
    high   (over 40)    -> read the fine print, full trial if the rules pass
"""
import re

from .precedents import precedents_for

# Words in the fine print that make an offer riskier, and how many points each adds.
SIGNALS = [
    (r"renew|subscription|membership|per (month|week|year)|/mo\b", 30, "Recurring-charge language in the fine print"),
    (r"\btrial\b|just \$|start today|first (box|month) for|introductory", 25, "Teaser or trial pricing"),
    (r"\bfee\b|handling|processing", 15, "Fee language at checkout"),
    (r"restocking|customer is responsible", 15, "Return costs in the fine print"),
]


def score_risk(offer, merchant, rules):
    """Return {"score": number, "tier": "low"|"medium"|"high", "reasons": [...], "precedents": [...]}."""
    all_text = "\n".join(line["text"] for line in offer["evidence"])
    reasons = []
    score = 0

    # 1) Has the merchant submitted a verified case file?
    case_file = merchant.get("caseFile") or {}
    if case_file.get("verified"):
        score = score - 25
        reasons.append({"points": -25, "label": "Trial-Tested merchant with a verified case file"})
    else:
        score = score + 15
        reasons.append({"points": 15, "label": "No verified case file"})

    # 2) Is it a big part of the budget?
    if offer["declared"]["totalDueToday"] >= rules["budget"] * 0.5:
        score = score + 10
        reasons.append({"points": 10, "label": "Half the budget or more"})

    # 3) Risky words in the fine print.
    for pattern, points, label in SIGNALS:
        if re.search(pattern, all_text, re.IGNORECASE):
            score = score + points
            reasons.append({"points": points, "label": label})

    # 4) Case law: has this merchant been caught before?
    priors = precedents_for(merchant["id"])
    if priors:
        points = min(60, len(priors) * 35)
        score = score + points
        plural = "s" if len(priors) > 1 else ""
        reasons.append({"points": points, "label": f"Case law: {len(priors)} prior rejection{plural} for this merchant"})

    # Turn the score into a tier.
    if score <= 10:
        tier = "low"
    elif score <= 40:
        tier = "medium"
    else:
        tier = "high"
    return {"score": score, "tier": tier, "reasons": reasons, "precedents": priors}
