r"""
graph.py - the per-offer decision flow, expressed as a LangGraph StateGraph.

This is an OPTIONAL alternative to trial.decide_offer(). It calls the exact same
agents (agents.py) and the exact same rules (rules.py); only the wiring between
the steps is a graph instead of if/else code. Nothing else in the project imports
this file, so the app, the tests, the evaluation and the benchmark are unchanged.

    pip install -r backend/requirements-langgraph.txt
    python -m backend.compare_graph        # proves both versions give the same verdicts

The graph:

    START -> route --(low risk + verified)--> code_only ------------------------> END
                   \-(everything else)----> check_rules
    check_rules --(hard rule failed)--> reject_by_code -------------------------> END
                \-(medium risk)-------> quick_check --(nothing critical)--> approve_quick -> END
                                                     \-(rule failed, old design)-> reject_after_quick -> END
                                                     \-(critical issue)--> trial_open
                \-(high risk)---------> trial_open
    trial_open -> prosecute  \
               -> defend      >-- both run in parallel --> judge -> END
"""
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import defend, judge, prosecute
from .config import settings
from .rules import check_rules, failed_rules
from .trial import is_verified, public_facts


class OfferState(TypedDict, total=False):
    # Inputs (the same arguments trial.decide_offer takes)
    offer: dict
    merchant: dict
    risk: dict
    facts: dict
    context: dict
    send: Any
    round_number: int
    client: Any
    metrics: Any
    # Filled in as the graph runs
    results: list
    failed: list
    prosecution: Optional[dict]
    defense: Optional[dict]
    outcome: dict


def _count_code_decision(metrics):
    with metrics.lock:
        metrics.decided_by_code = metrics.decided_by_code + 1


# ---------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------
def route(state):
    """Entry point. Decides nothing itself; the edges after it do the routing."""
    return {}


def code_only(state):
    """Low risk + verified merchant: check the verified case file with code, no AI."""
    merchant, tier, send, n = state["merchant"], state["risk"]["tier"], state["send"], state["round_number"]
    facts = dict(merchant["caseFile"]["facts"])
    facts["evidence"] = {"totalDueToday": [], "recurring": [], "returnCost": [], "hiddenFees": []}
    results = check_rules(facts, state["context"]["rules"])
    send({"type": "rules", "round": n, "results": results, "source": "Verified case file"})
    failed = failed_rules(results)
    _count_code_decision(state["metrics"])
    if failed:
        verdict = "REJECT"
        reasoning = "Verified terms break a rule: " + "; ".join(rule["rule"] for rule in failed) + "."
    else:
        verdict = "APPROVE"
        reasoning = "Trial-Tested merchant. Its verified terms pass every rule, so no AI and no trial are needed."
    send({"type": "verdict", "round": n, "tier": tier, "verdict": verdict, "decidedBy": "code",
          "reasoning": reasoning, "keyFindings": [], "facts": public_facts(facts)})
    return {"outcome": {"verdict": verdict, "facts": facts,
                        "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}}


def check_rules_node(state):
    """Show the facts read from the fine print, then check the buyer's hard rules."""
    send, n, facts = state["send"], state["round_number"], state["facts"]
    send({"type": "facts", "round": n, "mode": facts["mode"], "facts": public_facts(facts)})
    results = check_rules(facts, state["context"]["rules"])
    send({"type": "rules", "round": n, "results": results, "source": "Read from the fine print"})
    return {"results": results, "failed": failed_rules(results), "prosecution": None}


def reject_by_code(state):
    """A hard rule failed: the answer is already REJECT, so no AI and no trial."""
    failed, facts = state["failed"], state["facts"]
    _count_code_decision(state["metrics"])
    findings = [{"point": f"{rule['rule']}: {rule['detail']}", "evidence": rule["evidence"]} for rule in failed]
    state["send"]({"type": "verdict", "round": state["round_number"], "tier": state["risk"]["tier"],
                   "verdict": "REJECT", "decidedBy": "code",
                   "reasoning": "Rejected by code in milliseconds. A hard rule failed, and no AI can overrule it, so a trial would change nothing.",
                   "keyFindings": findings, "facts": public_facts(facts)})
    return {"outcome": {"verdict": "REJECT", "facts": facts,
                        "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}}


def quick_check(state):
    """Medium risk: one quick prosecutor pass."""
    quick = prosecute(state["offer"], state["facts"], state["context"], state["client"], state["metrics"], quick=True)
    state["send"]({"type": "argument", "round": state["round_number"], "agent": "prosecutor", "quick": True,
                   "mode": quick["mode"], "arguments": quick["arguments"], "dropped": quick["dropped"]})
    return {"prosecution": quick}


def reject_after_quick(state):
    """Old design only (SKIP_TRIAL_ON_RULE_FAIL=false): a rule failed, reject after the quick check."""
    failed, facts = state["failed"], state["facts"]
    state["send"]({"type": "verdict", "round": state["round_number"], "tier": state["risk"]["tier"],
                   "verdict": "REJECT", "decidedBy": "code", "reasoning": "A hard rule failed.",
                   "keyFindings": state["prosecution"]["arguments"][:2], "facts": public_facts(facts)})
    return {"outcome": {"verdict": "REJECT", "facts": facts,
                        "issues": [rule["detail"] for rule in failed], "decidedBy": "code"}}


def approve_quick(state):
    """Every rule passed and the quick check found nothing critical."""
    facts = state["facts"]
    state["send"]({"type": "verdict", "round": state["round_number"], "tier": state["risk"]["tier"],
                   "verdict": "APPROVE", "decidedBy": "quick check",
                   "reasoning": "Every rule passed and the quick check found nothing critical.",
                   "keyFindings": state["prosecution"]["arguments"], "facts": public_facts(facts)})
    return {"outcome": {"verdict": "APPROVE", "facts": facts, "issues": [], "decidedBy": "quick check"}}


def trial_open(state):
    """Open the trial. If a quick check escalated, say why first."""
    if state.get("prosecution") is not None:
        critical = [p for p in state["prosecution"]["arguments"] if p["severity"] == "critical"]
        state["send"]({"type": "escalate", "round": state["round_number"],
                       "reason": f"Every rule passed, but the quick check found {len(critical)} critical issue(s). This needs judgment, so it goes to trial."})
    state["send"]({"type": "trial_open", "round": state["round_number"]})
    return {}


def prosecute_node(state):
    """Prosecutor. Reuses the quick check if there was one, so no second call."""
    if state.get("prosecution") is not None:
        return {"prosecution": state["prosecution"]}
    return {"prosecution": prosecute(state["offer"], state["facts"], state["context"], state["client"], state["metrics"])}


def defend_node(state):
    """Defense. Runs in parallel with the prosecutor."""
    return {"defense": defend(state["offer"], state["facts"], state["context"], state["client"], state["metrics"])}


def judge_node(state):
    """Judge. Waits for both sides, then rules. Code still has the final word on hard rules (inside judge())."""
    send, n, facts = state["send"], state["round_number"], state["facts"]
    prosecution, defense = state["prosecution"], state["defense"]
    send({"type": "argument", "round": n, "agent": "prosecutor", "mode": prosecution["mode"],
          "arguments": prosecution["arguments"], "dropped": prosecution["dropped"]})
    send({"type": "argument", "round": n, "agent": "defense", "mode": defense["mode"],
          "arguments": defense["arguments"], "dropped": defense["dropped"]})
    ruling = judge(state["offer"], facts, state["context"], prosecution, defense,
                   state["results"], state["client"], state["metrics"])
    send({"type": "verdict", "round": n, "tier": state["risk"]["tier"], "verdict": ruling["verdict"],
          "decidedBy": "trial", "mode": ruling["mode"], "reasoning": ruling["reasoning"],
          "overruled": ruling.get("overruled"), "keyFindings": ruling["keyFindings"], "facts": public_facts(facts)})
    issues = [rule["detail"] for rule in state["failed"]]
    for point in prosecution["arguments"]:
        if point["severity"] == "critical":
            issues.append(point["point"])
    return {"outcome": {"verdict": ruling["verdict"], "facts": facts, "issues": issues, "decidedBy": "trial"}}


# ---------------------------------------------------------------
# Edges (the routing)
# ---------------------------------------------------------------
def after_route(state):
    if state["risk"]["tier"] == "low" and is_verified(state["merchant"]):
        return "code_only"
    return "check_rules"


def after_rules(state):
    if state["failed"] and settings.skip_trial_on_rule_fail:
        return "reject_by_code"
    if state["risk"]["tier"] == "medium":
        return "quick_check"
    return "trial_open"


def after_quick(state):
    if state["failed"]:
        return "reject_after_quick"
    critical = [p for p in state["prosecution"]["arguments"] if p["severity"] == "critical"]
    return "trial_open" if critical else "approve_quick"


def build_graph():
    graph = StateGraph(OfferState)
    graph.add_node("route", route)
    graph.add_node("code_only", code_only)
    graph.add_node("check_rules", check_rules_node)
    graph.add_node("reject_by_code", reject_by_code)
    graph.add_node("quick_check", quick_check)
    graph.add_node("reject_after_quick", reject_after_quick)
    graph.add_node("approve_quick", approve_quick)
    graph.add_node("trial_open", trial_open)
    graph.add_node("prosecute", prosecute_node)
    graph.add_node("defend", defend_node)
    graph.add_node("judge", judge_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", after_route, {"code_only": "code_only", "check_rules": "check_rules"})
    graph.add_conditional_edges("check_rules", after_rules, {
        "reject_by_code": "reject_by_code", "quick_check": "quick_check", "trial_open": "trial_open"})
    graph.add_conditional_edges("quick_check", after_quick, {
        "reject_after_quick": "reject_after_quick", "approve_quick": "approve_quick", "trial_open": "trial_open"})
    # Fan out: prosecutor and defense run in the same step (in parallel), then the judge waits for both.
    graph.add_edge("trial_open", "prosecute")
    graph.add_edge("trial_open", "defend")
    graph.add_edge(["prosecute", "defend"], "judge")
    for node in ("code_only", "reject_by_code", "reject_after_quick", "approve_quick", "judge"):
        graph.add_edge(node, END)
    return graph.compile()


_GRAPH = None


def decide_offer_graph(offer, merchant, risk, facts, context, send, round_number, client, metrics):
    """Drop-in replacement for trial.decide_offer, same arguments and same return value."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    final = _GRAPH.invoke({
        "offer": offer, "merchant": merchant, "risk": risk, "facts": facts, "context": context,
        "send": send, "round_number": round_number, "client": client, "metrics": metrics,
    })
    return final["outcome"]
