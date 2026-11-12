"""
trial.py - the courtroom. Runs one whole case.

  1. PayPal is already holding the money.
  2. Score every offer's risk (code, instant).
  3. Read the fine print of every offer that needs it, all at once (parallel),
     reusing saved facts when the text has not changed (cache).
  4. The shopping agent proposes the cheapest offer. For each proposal:
       verified merchant + low risk -> code checks the rules, no AI
       a hard rule fails            -> REJECT by code, no AI, no trial
       rules pass, medium risk      -> one quick AI check; a critical issue -> trial
       rules pass, high risk        -> trial: prosecutor + defense (parallel), then judge
  5. APPROVE -> PayPal captures the exact amount.  Nothing passes -> PayPal voids the hold.
  6. Show what the naive agent would have paid, the case metrics, and save a receipt.

emit(event) sends each step to the browser as it happens.
"""
from concurrent.futures import ThreadPoolExecutor

from .agents import defend, extract_facts, judge, prosecute, shopper_pick
from .catalog import get_merchant, get_scenario, offers_for
from .config import settings
from .facts_cache import get_cached_facts, save_facts
from .metrics import CaseMetrics
from .paypal_client import capture_authorization, void_authorization
from .precedents import record_precedent
from .receipts import save_receipt
from .risk import score_risk
from .rules import check_rules, failed_rules, hidden_total, true_year_cost


def usd(amount):
    return f"${float(amount):.2f}"


def is_verified(merchant):
    case_file = merchant.get("caseFile") or {}
    return bool(case_file.get("verified"))


def public_facts(facts):
    """The facts the browser shows, plus the first-year cost."""
    return {
        "totalDueToday": facts["totalDueToday"],
        "recurring": facts.get("recurring"),
        "returnCost": facts.get("returnCost"),
        "hiddenFees": facts.get("hiddenFees", []),
        "yearCost": round(true_year_cost(facts), 2),
        "safetyNet": facts.get("safetyNet", []),
    }


# ---------------------------------------------------------------
# Step 3: read the fine print (cache first, then the AI, in parallel)
# ---------------------------------------------------------------
def read_fine_print(offers, client, metrics, send):
    """Return {offer_id: facts} for these offers."""
    if not offers:
        return {}
    facts_by_offer = {}
    still_to_read = []

    # First, reuse facts we saved before for exactly the same text.
    for offer in offers:
        cached = get_cached_facts(offer)
        if cached:
            cached["mode"] = "cache"
            facts_by_offer[offer["id"]] = cached
            with metrics.lock:
                metrics.cache_hits = metrics.cache_hits + 1
        else:
            still_to_read.append(offer)

    # Then read the rest. In parallel, the wait is about ONE AI call instead of one per offer.
    use_threads = settings.parallel and len(still_to_read) > 1
    if use_threads:
        with ThreadPoolExecutor(max_workers=len(still_to_read)) as pool:
            results = list(pool.map(lambda offer: extract_facts(offer, client, metrics), still_to_read))
    else:
        results = [extract_facts(offer, client, metrics) for offer in still_to_read]

    for offer, facts in zip(still_to_read, results):
        facts_by_offer[offer["id"]] = facts
        if facts["mode"] in ("live", "mock"):     # only save real AI answers, not fallbacks
            save_facts(offer, facts)

    send({
        "type": "reading",
        "offers": [offer["title"] for offer in offers],
        "fromCache": len(offers) - len(still_to_read),
        "parallel": use_threads,
    })
    return facts_by_offer


# ---------------------------------------------------------------
# Step 4: decide one offer
# ---------------------------------------------------------------
def decide_offer(offer, merchant, risk, facts, context, send, round_number, client, metrics):
    """Decide one offer. Returns {"verdict", "facts", "issues", "decidedBy"}."""
    tier = risk["tier"]

    # --- Low risk + verified merchant: code only, no AI ---
    if tier == "low" and is_verified(merchant):
        facts = dict(merchant["caseFile"]["facts"])
        facts["evidence"] = {"totalDueToday": [], "recurring": [], "returnCost": [], "hiddenFees": []}
        results = check_rules(facts, context["rules"])
        send({"type": "rules", "round": round_number, "results": results, "source": "Verified case file"})
        failed = failed_rules(results)
        with metrics.lock:
            metrics.decided_by_code = metrics.decided_by_code + 1
        if failed:
            verdict = "REJECT"
            reasoning = "Verified terms break a rule: " + "; ".join(rule["rule"] for rule in failed) + "."
        else:
            verdict = "APPROVE"
            reasoning = "Trial-Tested merchant. Its verified terms pass every rule, so no AI and no trial are needed."
        send({"type": "verdict", "round": round_number, "tier": tier, "verdict": verdict, "decidedBy": "code",
              "reasoning": reasoning, "keyFindings": [], "facts": public_facts(facts)})
        return {"verdict": verdict, "facts": facts, "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}

    # --- Everyone else: show the facts read from the fine print, then check the rules ---
    send({"type": "facts", "round": round_number, "mode": facts["mode"], "facts": public_facts(facts)})
    results = check_rules(facts, context["rules"])
    send({"type": "rules", "round": round_number, "results": results, "source": "Read from the fine print"})
    failed = failed_rules(results)

    # --- A hard rule failed: the answer is already REJECT, so skip the AI trial ---
    if failed and settings.skip_trial_on_rule_fail:
        with metrics.lock:
            metrics.decided_by_code = metrics.decided_by_code + 1
        findings = [{"point": f"{rule['rule']}: {rule['detail']}", "evidence": rule["evidence"]} for rule in failed]
        send({"type": "verdict", "round": round_number, "tier": tier, "verdict": "REJECT", "decidedBy": "code",
              "reasoning": "Rejected by code in milliseconds. A hard rule failed, and no AI can overrule it, so a trial would change nothing.",
              "keyFindings": findings, "facts": public_facts(facts)})
        return {"verdict": "REJECT", "facts": facts, "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}

    prosecution = None
    # --- Medium risk: one quick AI check ---
    if tier == "medium":
        quick = prosecute(offer, facts, context, client, metrics, quick=True)
        send({"type": "argument", "round": round_number, "agent": "prosecutor", "quick": True,
              "mode": quick["mode"], "arguments": quick["arguments"], "dropped": quick["dropped"]})
        critical = [point for point in quick["arguments"] if point["severity"] == "critical"]

        if failed:   # only reached in the old design (SKIP_TRIAL_ON_RULE_FAIL=false)
            send({"type": "verdict", "round": round_number, "tier": tier, "verdict": "REJECT", "decidedBy": "code",
                  "reasoning": "A hard rule failed.", "keyFindings": quick["arguments"][:2], "facts": public_facts(facts)})
            return {"verdict": "REJECT", "facts": facts, "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}

        if not critical:
            send({"type": "verdict", "round": round_number, "tier": tier, "verdict": "APPROVE", "decidedBy": "quick check",
                  "reasoning": "Every rule passed and the quick check found nothing critical.",
                  "keyFindings": quick["arguments"], "facts": public_facts(facts)})
            return {"verdict": "APPROVE", "facts": facts, "issues": [], "decidedBy": "quick check"}

        send({"type": "escalate", "round": round_number,
              "reason": f"Every rule passed, but the quick check found {len(critical)} critical issue(s). This needs judgment, so it goes to trial."})
        prosecution = quick   # reuse the quick check as the prosecution: no second call

    # --- Full trial ---
    send({"type": "trial_open", "round": round_number})
    if prosecution is not None:
        defense = defend(offer, facts, context, client, metrics)
    elif settings.parallel:
        # The prosecutor and the defense don't need each other, so run them at the same time.
        with ThreadPoolExecutor(max_workers=2) as pool:
            prosecution_job = pool.submit(prosecute, offer, facts, context, client, metrics)
            defense_job = pool.submit(defend, offer, facts, context, client, metrics)
            prosecution = prosecution_job.result()
            defense = defense_job.result()
    else:
        prosecution = prosecute(offer, facts, context, client, metrics)
        defense = defend(offer, facts, context, client, metrics)

    send({"type": "argument", "round": round_number, "agent": "prosecutor", "mode": prosecution["mode"],
          "arguments": prosecution["arguments"], "dropped": prosecution["dropped"]})
    send({"type": "argument", "round": round_number, "agent": "defense", "mode": defense["mode"],
          "arguments": defense["arguments"], "dropped": defense["dropped"]})

    ruling = judge(offer, facts, context, prosecution, defense, results, client, metrics)
    send({"type": "verdict", "round": round_number, "tier": tier, "verdict": ruling["verdict"], "decidedBy": "trial",
          "mode": ruling["mode"], "reasoning": ruling["reasoning"], "overruled": ruling.get("overruled"),
          "keyFindings": ruling["keyFindings"], "facts": public_facts(facts)})

    issues = [rule["detail"] for rule in failed]
    for point in prosecution["arguments"]:
        if point["severity"] == "critical":
            issues.append(point["point"])
    return {"verdict": ruling["verdict"], "facts": facts, "issues": issues, "decidedBy": "trial"}


# ---------------------------------------------------------------
# The whole case
# ---------------------------------------------------------------
def run_case(scenario_id, rules, authorization, emit, client=None, order_id=None):
    """
    Run one case from PayPal hold to capture or void.
    client=None runs every agent offline; pass llm.make_client() for the real AI.
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise ValueError("Unknown scenario")
    context = {"request": scenario["request"], "protectedPerson": scenario["protectedPerson"], "rules": rules}
    metrics = CaseMetrics()
    events = []

    def send(event):
        """Send an event to the browser and keep a copy for the receipt."""
        events.append(event)
        emit(event)

    send({"type": "hold", "authorizationId": authorization["authorizationId"], "amount": authorization["amount"]})

    # The shopping agent looks at offers cheapest first.
    candidates = sorted(offers_for(scenario_id), key=lambda offer: offer["declared"]["totalDueToday"])
    naive_choice = candidates[0]   # what an agent without Countersign would buy

    # Step 2: risk for every offer (instant).
    risks = {}
    for offer in candidates:
        risks[offer["id"]] = score_risk(offer, get_merchant(offer["merchantId"]), rules)

    # Step 3: read the fine print of everything that needs reading, up front and in parallel.
    needs_reading = []
    for offer in candidates:
        merchant = get_merchant(offer["merchantId"])
        if not (risks[offer["id"]]["tier"] == "low" and is_verified(merchant)):
            needs_reading.append(offer)
    facts_by_offer = {}
    if settings.parallel:
        facts_by_offer = read_fine_print(needs_reading, client, metrics, send)

    # Step 4: propose, decide, and either buy or send the agent back.
    history = []
    remaining = list(candidates)
    round_number = 0
    approved = None
    while remaining:
        round_number = round_number + 1
        pick = shopper_pick(scenario["request"], remaining, client, metrics)
        offer = next(item for item in remaining if item["id"] == pick["offerId"])
        merchant = get_merchant(offer["merchantId"])
        risk = risks[offer["id"]]
        send({"type": "proposal", "round": round_number, "mode": pick["mode"], "reason": pick["reason"],
              "offer": {"id": offer["id"], "title": offer["title"], "merchant": merchant["name"],
                        "trialTested": is_verified(merchant), "advertised": offer["displayPrice"],
                        "evidence": offer["evidence"]}})
        send({"type": "risk", "round": round_number, "score": risk["score"], "tier": risk["tier"],
              "reasons": risk["reasons"], "precedents": len(risk["precedents"])})

        facts = facts_by_offer.get(offer["id"])
        if facts is None and offer in needs_reading:     # old design: read one offer at a time
            facts = read_fine_print([offer], client, metrics, send)[offer["id"]]
            facts_by_offer[offer["id"]] = facts

        outcome = decide_offer(offer, merchant, risk, facts, context, send, round_number, client, metrics)
        history.append({
            "offerId": offer["id"], "title": offer["title"], "merchant": merchant["name"], "tier": risk["tier"],
            "verdict": outcome["verdict"], "decidedBy": outcome["decidedBy"],
            "facts": public_facts(outcome["facts"]), "issues": outcome["issues"][:3],
        })

        if outcome["verdict"] == "APPROVE":
            approved = (offer, merchant, outcome["facts"])
            break

        record_precedent({"merchantId": merchant["id"], "offerId": offer["id"], "issues": outcome["issues"][:3]})
        remaining.remove(offer)
        send({"type": "sent_back", "round": round_number, "remaining": len(remaining)})

    # Step 5: move the money, or release it.
    payment = {"orderId": order_id, "authorizationId": authorization["authorizationId"], "paypalMode": settings.paypal_mode}
    if approved:
        offer, merchant, facts = approved
        capture = capture_authorization(authorization["authorizationId"], facts["totalDueToday"], f"Countersign approved: {offer['title']}")
        released = round(authorization["amount"] - facts["totalDueToday"], 2)
        payment.update({"action": "capture", "captureId": capture["captureId"], "amount": facts["totalDueToday"], "released": released})
        send({"type": "payment", "action": "capture", "amount": facts["totalDueToday"], "released": released, "captureId": capture["captureId"]})
    else:
        void_authorization(authorization["authorizationId"])
        payment.update({"action": "void", "captureId": None, "amount": 0, "released": authorization["amount"]})
        send({"type": "payment", "action": "void", "amount": 0, "released": authorization["amount"]})

    # Step 6a: what would an agent WITHOUT Countersign have paid?
    naive_facts = facts_by_offer.get(naive_choice["id"])
    if naive_facts is None:   # the cheapest offer was a verified merchant
        naive_facts = get_merchant(naive_choice["merchantId"])["caseFile"]["facts"]
    naive_year = round(true_year_cost(naive_facts), 2)
    chosen_year = round(true_year_cost(approved[2]), 2) if approved else 0.0
    counterfactual = {
        "naiveTitle": naive_choice["title"],
        "naiveMerchant": get_merchant(naive_choice["merchantId"])["name"],
        "naiveAdvertised": naive_choice["displayPrice"],
        "naiveYearCost": naive_year,
        "chosenTitle": approved[0]["title"] if approved else None,
        "chosenYearCost": chosen_year,
        "saved": round(max(0.0, naive_year - chosen_year), 2),
    }
    send({"type": "counterfactual", **counterfactual})

    # Step 6b: the numbers for this case.
    case_metrics = metrics.summary()
    send({"type": "metrics", "aiMode": settings.llm_mode, "flags": settings.efficiency_flags(), **case_metrics})
    send({"type": "summary", "text": guardian_summary(scenario, history, approved)})

    # Step 6c: the receipt (tamper-evident, chained to the previous one).
    receipt = save_receipt({
        "scenario": scenario_id, "request": scenario["request"], "protectedPerson": scenario["protectedPerson"],
        "rules": rules, "outcome": "approved" if approved else "voided", "payment": payment,
        "aiMode": settings.llm_mode, "flags": settings.efficiency_flags(), "offers": history,
        "counterfactual": counterfactual, "metrics": case_metrics, "events": events,
    })
    emit({"type": "receipt", "id": receipt["id"], "hash": receipt["hash"], "previousHash": receipt["previousHash"]})
    return {"status": "approved" if approved else "voided", "history": history, "metrics": case_metrics,
            "counterfactual": counterfactual, "receipt": receipt}


def guardian_summary(scenario, history, approved):
    """Plain English for the guardian: what was blocked, and what was bought."""
    person = scenario["protectedPerson"]
    lines = []
    for item in history:
        if item["verdict"] != "REJECT":
            continue
        facts = item["facts"]
        if facts.get("recurring"):
            renew = facts["recurring"]
            lines.append(f"Blocked {item['merchant']}: advertised cheap, but it renews at {usd(renew['amount'])} per {renew['interval']} (about {usd(facts['yearCost'])} in the first year).")
        elif facts.get("hiddenFees"):
            lines.append(f"Blocked {item['merchant']}: {usd(hidden_total(facts))} in fees that were not on the product page.")
        elif item["issues"]:
            lines.append(f"Blocked {item['merchant']}: {item['issues'][0]}")
        else:
            lines.append(f"Blocked {item['merchant']}: it broke one of your rules.")
    if approved:
        offer, merchant, facts = approved
        returns = ", with free returns" if facts.get("returnCost") == 0 else ""
        tested = " (Trial-Tested merchant)" if is_verified(merchant) else ""
        lines.append(f"Bought for {person}: {offer['title']} from {merchant['name']} for {usd(facts['totalDueToday'])}, one time{returns}{tested}. Nothing else will be charged.")
    else:
        lines.append(f"Nothing was bought for {person}. Every option hid a charge or broke your rules, so PayPal released the hold and {person} was not charged.")
    return "\n".join(lines)
