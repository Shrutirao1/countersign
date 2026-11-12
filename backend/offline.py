"""
offline.py - the agents' offline analyzers (no AI, just pattern matching).

They read the same fine-print text as the AI, using regular expressions.
They are used when:
  - there is no API key (offline mode),
  - an AI call fails or times out (fallback, so a case always finishes),
  - mock mode (to test speed without paying for AI).

They are also the BASELINE in the evaluation: the scoreboard compares them to
the real AI. They were written for the demo's wording, so they miss traps that
are worded differently. That gap is the reason the AI is worth its cost.
"""
import re

from .rules import true_year_cost

# A claim on the product page, and fine print that takes it back.
CLAIM_WORDS = r"clinically validated|validated|certified|medical-grade|lifetime|waterproof|guaranteed"
DISCLAIMERS = r"not intended for|refers to the original|does not cover|not covered|splash resistant only|not suitable for|limited to \d+|void if"


def usd(amount):
    return f"${float(amount):.2f}"


def is_from(line, source_word):
    """True if an evidence line comes from a source like 'Checkout' or 'Return Policy'."""
    return re.search(source_word, line["source"], re.IGNORECASE) is not None


def empty_evidence():
    return {"totalDueToday": [], "recurring": [], "returnCost": [], "hiddenFees": []}


# ---------------------------------------------------------------
# Fine-print reader
# ---------------------------------------------------------------
def extract_offline(offer):
    """Turn the fine print into numbers: total today, recurring charge, return cost, hidden fees."""
    cited = empty_evidence()
    checkout_lines = [line for line in offer["evidence"] if is_from(line, "checkout")]

    # 1) Total due today: the last "Total $X" at checkout.
    total = offer["declared"]["totalDueToday"]
    for line in checkout_lines:
        matches = re.findall(r"\btotal(?:\s+today)?:?\s*\$([\d,]+(?:\.\d+)?)", line["text"], re.IGNORECASE)
        if matches:
            total = float(matches[-1].replace(",", ""))
            cited["totalDueToday"] = [line["id"]]

    # 2) Recurring charge: "renews automatically at $X per month".
    recurring = None
    for line in offer["evidence"]:
        match = re.search(r"renews? automatically at \$(\d+(?:\.\d+)?) per (week|month|year)", line["text"], re.IGNORECASE)
        if match:
            recurring = {"amount": float(match.group(1)), "interval": match.group(2).lower()}
            cited["recurring"] = [line["id"]]

    # 3) Return cost: restocking fee % and return shipping, from the Return Policy.
    return_cost = None
    for line in offer["evidence"]:
        if not is_from(line, "return policy"):
            continue
        percent = re.search(r"(\d+)%\s*restocking fee[^$]*\$(\d+(?:\.\d+)?)", line["text"], re.IGNORECASE)
        shipping = re.search(r"return shipping[^$]*\$(\d+(?:\.\d+)?)", line["text"], re.IGNORECASE)
        if percent or shipping:
            cost = 0.0
            if percent:
                cost = cost + float(percent.group(1)) / 100 * float(percent.group(2))
            if shipping:
                cost = cost + float(shipping.group(1))
            return_cost = round(cost, 2)
            cited["returnCost"] = [line["id"]]
        elif re.search(r"free returns", line["text"], re.IGNORECASE):
            return_cost = 0
            cited["returnCost"] = [line["id"]]

    # 4) Hidden fees: only if checkout costs more than the advertised price.
    hidden = []
    if total > offer["displayPrice"] + 0.001:
        for line in checkout_lines:
            for label, amount in re.findall(r"([A-Za-z&\s]+?(?:fee|shipping))\s*\$(\d+(?:\.\d+)?)", line["text"], re.IGNORECASE):
                hidden.append({"label": label.strip(), "amount": float(amount)})
                if line["id"] not in cited["hiddenFees"]:
                    cited["hiddenFees"].append(line["id"])
        if not hidden:
            hidden.append({"label": "Unexplained difference", "amount": round(total - offer["displayPrice"], 2)})
            cited["hiddenFees"] = cited["totalDueToday"]

    return {"totalDueToday": total, "recurring": recurring, "returnCost": return_cost, "hiddenFees": hidden, "evidence": cited}


# ---------------------------------------------------------------
# Prosecutor: argues AGAINST the purchase
# ---------------------------------------------------------------
def prosecute_offline(offer, facts):
    points = []
    cited = facts["evidence"]

    # A renewal hidden behind a low price.
    if facts.get("recurring"):
        renew = facts["recurring"]
        points.append({
            "point": f"This is not a one-time purchase. After {usd(facts['totalDueToday'])} today it renews at {usd(renew['amount'])} per {renew['interval']}. First-year cost is about {usd(true_year_cost(facts))}.",
            "severity": "critical",
            "evidence": cited["recurring"] + cited["totalDueToday"],
        })

    # "Free returns" on the product page, but returns cost money.
    free_claim = None
    for line in offer["evidence"]:
        if re.search(r"free returns", line["text"], re.IGNORECASE) and not is_from(line, "return policy"):
            free_claim = line
    if free_claim and (facts.get("returnCost") or 0) > 0:
        points.append({
            "point": f"Claim not supported: the product page promises free returns, but the return policy means sending it back costs about {usd(facts['returnCost'])}.",
            "severity": "critical",
            "evidence": [free_claim["id"]] + cited["returnCost"],
        })

    # Fees that only appear at checkout.
    if facts.get("hiddenFees"):
        total_fees = sum(fee["amount"] for fee in facts["hiddenFees"])
        product_ids = [line["id"] for line in offer["evidence"] if is_from(line, "product page")][:1]
        points.append({
            "point": f"Advertised at {usd(offer['displayPrice'])}, but checkout adds {usd(total_fees)} in fees that were never shown on the product page.",
            "severity": "major",
            "evidence": cited["hiddenFees"] + product_ids,
        })

    # A product-page claim that the fine print takes back.
    for claim_line in offer["evidence"]:
        if not is_from(claim_line, "product page"):
            continue
        claim = re.search(CLAIM_WORDS, claim_line["text"], re.IGNORECASE)
        if not claim:
            continue
        for other in offer["evidence"]:
            if other is claim_line or is_from(other, "product page"):
                continue
            if re.search(DISCLAIMERS, other["text"], re.IGNORECASE):
                points.append({
                    "point": f"Claim not supported: the product page says \"{claim.group(0)}\", but the fine print says: \"{other['text']}\"",
                    "severity": "critical",
                    "evidence": [claim_line["id"], other["id"]],
                })
                break

    # Smaller traps.
    for line in offer["evidence"]:
        fee = re.search(r"cancellation fee:?\s*\$(\d+(?:\.\d+)?)", line["text"], re.IGNORECASE)
        if fee:
            points.append({"point": f"Leaving early costs an extra {usd(fee.group(1))}.", "severity": "major", "evidence": [line["id"]]})
        if re.search(r"by phone", line["text"], re.IGNORECASE):
            points.append({"point": "Cancelling needs a phone call during limited hours, so the renewal is hard to stop.", "severity": "minor", "evidence": [line["id"]]})

    return {"arguments": points, "dropped": 0}


# ---------------------------------------------------------------
# Defense: argues FOR the purchase
# ---------------------------------------------------------------
def defend_offline(offer, facts, rules):
    points = []
    product = None
    for line in offer["evidence"]:
        if is_from(line, "product page"):
            product = line
            break
    if product:
        points.append({"point": f"It matches the request: a {offer['category']}.", "severity": "major", "evidence": [product["id"]]})
    if facts["totalDueToday"] <= rules["budget"]:
        cite = facts["evidence"]["totalDueToday"] or [offer["evidence"][0]["id"]]
        points.append({"point": f"The amount due today, {usd(facts['totalDueToday'])}, is within the {usd(rules['budget'])} budget.", "severity": "major", "evidence": cite})
    if facts.get("returnCost") == 0 and facts["evidence"]["returnCost"]:
        points.append({"point": "Returns are free if it is not right.", "severity": "minor", "evidence": facts["evidence"]["returnCost"]})
    return {"arguments": points, "dropped": 0}


# ---------------------------------------------------------------
# Judge: decides
# ---------------------------------------------------------------
def judge_offline(prosecution, rule_results):
    failed = [result for result in rule_results if not result["passed"]]
    critical = [point for point in prosecution["arguments"] if point["severity"] == "critical"]

    if failed or critical:
        verdict = "REJECT"
        reasoning = "The defense shows the item fits the request, but "
        if critical:
            reasoning = reasoning + f"the prosecution proved {len(critical)} critical issue(s) with evidence."
        else:
            reasoning = reasoning + "it breaks the guardian's rules."
    else:
        verdict = "APPROVE"
        reasoning = "The prosecution raised no critical issues and every rule passed."

    majors = [point for point in prosecution["arguments"] if point["severity"] == "major"]
    findings = [{"point": point["point"], "evidence": point["evidence"]} for point in (critical + majors)[:3]]
    return {"verdict": verdict, "reasoning": reasoning, "keyFindings": findings}
