"""
agents.py - the AI agents.

    shopper_pick   picks the cheapest offer (plain code by default, no AI needed)
    extract_facts  reads the fine print and turns it into numbers
    prosecute      argues AGAINST the purchase (also used as the quick check)
    defend         argues FOR the purchase
    judge          decides gray areas; a failed code rule always means REJECT

Each agent has a live version (asks the AI) and an offline version (offline.py).
run_agent() picks which one to use, measures it, and falls back to offline
if the AI fails, so a case ALWAYS finishes.

We never trust the AI blindly:
  - every reply is checked against a pydantic model (schemas.py),
  - citations to evidence that does not exist are removed,
  - a point with no real evidence left is dropped.
"""
import json
import time

from .config import settings
from .llm import ask
from .offline import defend_offline, extract_offline, judge_offline, prosecute_offline
from .schemas import ArgumentList, ExtractedFacts, Ruling, ShopperPick

FACT_NAMES = ("totalDueToday", "recurring", "returnCost", "hiddenFees")


def usd(amount):
    return f"${float(amount):.2f}"


def evidence_block(offer):
    """The fine print as numbered lines, for the AI to read and cite."""
    lines = []
    for line in offer["evidence"]:
        lines.append(f"[{line['id']}] ({line['source']}) {line['text']}")
    return "\n".join(lines)


def real_ids(offer, ids):
    """Keep only evidence IDs that really exist in this offer."""
    existing = [line["id"] for line in offer["evidence"]]
    return [one_id for one_id in (ids or []) if one_id in existing]


def clean_arguments(offer, reply):
    """Remove fake citations; drop any point left with no real evidence."""
    kept = []
    dropped = 0
    for argument in reply.arguments:
        cited = real_ids(offer, argument.evidence)
        if not cited:
            dropped = dropped + 1
            continue
        kept.append({"point": argument.point, "severity": argument.severity, "evidence": cited})
    return {"arguments": kept, "dropped": dropped}


def facts_for_prompt(facts):
    """Facts without our bookkeeping fields, for putting into a prompt."""
    return {name: facts.get(name) for name in FACT_NAMES}


def run_agent(name, client, metrics, model, live_function, offline_function, prompt_size):
    """
    Run one agent step and record what it cost.

    client is None      -> offline analyzer, no AI
    client.kind "mock"  -> offline answer after a fake delay (counts as an AI call)
    client.kind "live"  -> the real AI; if it fails, the offline analyzer answers
    """
    if client is None:
        result = offline_function()
        result["mode"] = "offline"
        with metrics.lock:
            metrics.offline_steps = metrics.offline_steps + 1
        return result

    start = time.time()

    if client.kind == "mock":
        time.sleep(settings.mock_latency_s)
        result = offline_function()
        # Estimate tokens: about 4 characters per token, plus the instructions.
        metrics.record_call(name, model, "mock", prompt_size // 4 + 300, 250, time.time() - start)
        result["mode"] = "mock"
        return result

    try:
        result, usage = live_function()
        metrics.record_call(name, model, "live", usage["input"], usage["output"], time.time() - start)
        result["mode"] = "live"
        return result
    except Exception as err:   # bad reply after retry, timeout, API error...
        reason = str(err)[:200]
        print(f"[{name}] AI call failed, using the offline analyzer: {reason}")
        metrics.record_call(name, model, "live", 0, 0, time.time() - start, fallback_reason=reason)
        result = offline_function()
        result["mode"] = "offline"
        result["fallbackReason"] = reason
        return result


# ---------------------------------------------------------------
# Shopper
# ---------------------------------------------------------------
def shopper_pick(request, candidates, client, metrics):
    """Pick the cheapest offer. Plain code is enough, so no AI call by default."""
    cheapest = min(candidates, key=lambda offer: offer["declared"]["totalDueToday"])
    code_answer = {"offerId": cheapest["id"], "reason": f"Lowest upfront price: {usd(cheapest['declared']['totalDueToday'])}."}

    if not settings.shopper_uses_ai:
        result = dict(code_answer)
        result["mode"] = "code"
        return result

    # Old design (kept so the benchmark can compare): ask the AI to pick.
    listing = "\n".join(f"- {offer['id']}: {offer['title']}, advertised {usd(offer['declared']['totalDueToday'])}" for offer in candidates)

    def live():
        reply, usage = ask(
            client, ShopperPick,
            "You are a shopping agent. Pick the offer with the lowest advertised upfront price. One-sentence reason.",
            f'Request: {request}\n\nOffers:\n{listing}\n\nReturn {{"offerId": "...", "reason": "..."}}',
            settings.fast_model, max_tokens=200,
        )
        if reply.offerId not in [offer["id"] for offer in candidates]:
            raise ValueError(f"shopper picked an unknown offer {reply.offerId!r}")
        return {"offerId": reply.offerId, "reason": reply.reason}, usage

    return run_agent("shopper", client, metrics, settings.fast_model, live, lambda: dict(code_answer), len(listing))


# ---------------------------------------------------------------
# Safety net: the AI's reading, double-checked by the free pattern matcher
# ---------------------------------------------------------------
def add_safety_net(ai_facts, rule_facts):
    """
    Combine what the AI read with what the pattern matcher read, always keeping
    the more cautious answer. So if EITHER one finds a renewal, a fee or a
    return cost, the guardian's rules see it. The AI can never miss a trap that
    plain pattern matching would have caught. This costs nothing: no extra AI call.
    """
    facts = dict(ai_facts)
    evidence = {name: list(ai_facts["evidence"].get(name, [])) for name in FACT_NAMES}
    caught = []   # what the safety net added, shown in the app

    # Total due today: keep the higher total.
    if rule_facts["totalDueToday"] > ai_facts["totalDueToday"] + 0.001:
        facts["totalDueToday"] = rule_facts["totalDueToday"]
        evidence["totalDueToday"] = rule_facts["evidence"]["totalDueToday"]
        caught.append("total")

    # A renewal the AI missed.
    if ai_facts["recurring"] is None and rule_facts["recurring"] is not None:
        facts["recurring"] = rule_facts["recurring"]
        evidence["recurring"] = rule_facts["evidence"]["recurring"]
        caught.append("renewal")

    # Return cost: keep the higher cost; if the AI didn't find one, use the rule's.
    ai_cost = ai_facts["returnCost"]
    rule_cost = rule_facts["returnCost"]
    if rule_cost is not None and (ai_cost is None or rule_cost > ai_cost + 0.001):
        facts["returnCost"] = rule_cost
        evidence["returnCost"] = rule_facts["evidence"]["returnCost"]
        if rule_cost > 0:
            caught.append("return cost")

    # Hidden fees the AI missed.
    if not ai_facts["hiddenFees"] and rule_facts["hiddenFees"]:
        facts["hiddenFees"] = rule_facts["hiddenFees"]
        evidence["hiddenFees"] = rule_facts["evidence"]["hiddenFees"]
        caught.append("hidden fees")

    facts["evidence"] = evidence
    facts["safetyNet"] = caught
    return facts


# ---------------------------------------------------------------
# Fine-print reader
# ---------------------------------------------------------------
def extract_facts(offer, client, metrics):
    prompt = f"""Advertised price: {usd(offer['displayPrice'])}

Evidence:
{evidence_block(offer)}

Return:
{{
  "totalDueToday": number,
  "recurring": null or {{"amount": number, "interval": "week" | "month" | "year"}},
  "returnCost": number (0 if returns are truly free, null if the text does not say),
  "hiddenFees": [{{"label": string, "amount": number}}],
  "evidence": {{"totalDueToday": [ids], "recurring": [ids], "returnCost": [ids], "hiddenFees": [ids]}}
}}
hiddenFees = charges added on top of the advertised price."""

    def live():
        reply, usage = ask(
            client, ExtractedFacts,
            "You read a product page, checkout and fine print and extract billing facts. "
            "Read every line. Only state what the text supports. Cite evidence IDs for each fact.",
            prompt, settings.fast_model, max_tokens=500,
        )
        facts = {
            "totalDueToday": reply.totalDueToday,
            "recurring": reply.recurring.model_dump() if reply.recurring else None,
            "returnCost": reply.returnCost,
            "hiddenFees": [fee.model_dump() for fee in reply.hiddenFees],
            "evidence": {name: real_ids(offer, reply.evidence.get(name)) for name in FACT_NAMES},
        }
        return add_safety_net(facts, extract_offline(offer)), usage

    return run_agent("extractor", client, metrics, settings.fast_model, live, lambda: extract_offline(offer), len(prompt))


# ---------------------------------------------------------------
# Prosecutor (and quick check)
# ---------------------------------------------------------------
def prosecute(offer, facts, context, client, metrics, quick=False):
    prompt = (
        f"Purchase request: {context['request']}\nProtected buyer: {context['protectedPerson']}\n"
        f"Buyer's rules: {json.dumps(context['rules'])}\nExtracted facts: {json.dumps(facts_for_prompt(facts))}\n\n"
        f"Evidence:\n{evidence_block(offer)}\n\n"
        'Return {"arguments": [{"point": string, "severity": "critical" | "major" | "minor", "evidence": [ids]}]}'
    )
    extra = " This is a quick check: list only the top issues." if quick else ""

    def live():
        reply, usage = ask(
            client, ArgumentList,
            "You are the PROSECUTOR deciding whether an AI shopping agent may spend someone's money. "
            "Argue against the purchase. Look for hidden fees, auto-renewals, cancellation traps, and product-page "
            "claims that the fine print contradicts. Every point must cite evidence IDs. Never invent facts. "
            "A product-page promise (lifetime, warranty, certified, like new, guaranteed, free) that the fine print takes back, "
            "limits, or excludes part of is ALWAYS critical, for example a 'lifetime' warranty limited to 90 days, or a "
            "'fully certified' laptop whose certification excludes the screen. A caveat that does not shrink the promise "
            "(colors may vary slightly) is minor. "
            'Severity: "critical" = the buyer would be misled or pay far more than expected; "major" = real extra cost; '
            '"minor" = friction.' + extra,
            prompt, settings.fast_model, max_tokens=600,
        )
        return clean_arguments(offer, reply), usage

    name = "quick check" if quick else "prosecutor"
    return run_agent(name, client, metrics, settings.fast_model, live, lambda: prosecute_offline(offer, facts), len(prompt))


# ---------------------------------------------------------------
# Defense
# ---------------------------------------------------------------
def defend(offer, facts, context, client, metrics):
    prompt = (
        f"Purchase request: {context['request']}\nBuyer's rules: {json.dumps(context['rules'])}\n"
        f"Extracted facts: {json.dumps(facts_for_prompt(facts))}\n\nEvidence:\n{evidence_block(offer)}\n\n"
        'Return {"arguments": [{"point": string, "severity": "critical" | "major" | "minor", "evidence": [ids]}]}'
    )

    def live():
        reply, usage = ask(
            client, ArgumentList,
            "You are the DEFENSE deciding whether an AI shopping agent may spend someone's money. "
            "Make the honest case FOR this purchase. Every point must cite evidence IDs. "
            "Do not deny facts the evidence shows; if something is weak, admit it.",
            prompt, settings.fast_model, max_tokens=500,
        )
        return clean_arguments(offer, reply), usage

    return run_agent("defense", client, metrics, settings.fast_model, live, lambda: defend_offline(offer, facts, context["rules"]), len(prompt))


# ---------------------------------------------------------------
# Judge
# ---------------------------------------------------------------
def judge(offer, facts, context, prosecution, defense, rule_results, client, metrics):
    prompt = (
        f"Purchase request: {context['request']}\nBuyer's rules: {json.dumps(context['rules'])}\n"
        f"Rule checks (done by code): {json.dumps(rule_results)}\nFacts: {json.dumps(facts_for_prompt(facts))}\n\n"
        f"Prosecution: {json.dumps(prosecution['arguments'])}\nDefense: {json.dumps(defense['arguments'])}\n\n"
        f"Evidence:\n{evidence_block(offer)}\n\n"
        'Return {"verdict": "APPROVE" | "REJECT", "reasoning": string, "keyFindings": [{"point": string, "evidence": [ids]}]}'
    )

    def live():
        reply, usage = ask(
            client, Ruling,
            "You are the JUDGE. Weigh the prosecution and the defense against the evidence and the buyer's rules. "
            "Only rely on points that cite real evidence. Reject if the buyer would be misled or would pay "
            "meaningfully more than they expected. A product-page promise that the fine print takes back, limits, or "
            "excludes part of is misleading, so reject it. Keep the reasoning to two sentences.",
            prompt, settings.judge_model, max_tokens=500,
        )
        findings = []
        for finding in reply.keyFindings:
            cited = real_ids(offer, finding.evidence)
            if cited:
                findings.append({"point": finding.point, "evidence": cited})
        return {"verdict": reply.verdict, "reasoning": reply.reasoning, "keyFindings": findings}, usage

    result = run_agent("judge", client, metrics, settings.judge_model, live, lambda: judge_offline(prosecution, rule_results), len(prompt))

    # Code has the final word: the judge can never approve past a failed rule.
    failed = [rule for rule in rule_results if not rule["passed"]]
    if failed and result["verdict"] == "APPROVE":
        result["verdict"] = "REJECT"
        result["overruled"] = "Overruled by code: " + "; ".join(rule["rule"] for rule in failed) + "."
    return result
