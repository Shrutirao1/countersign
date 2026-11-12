"""The agents: offline analyzers, and the live code path tested with fake models."""
import json

from backend.agents import defend, extract_facts, judge, prosecute, shopper_pick
from backend.catalog import OFFERS, STANDARD_RULES
from backend.config import settings
from backend.llm import MockClient, extract_json
from backend.metrics import CaseMetrics
from backend.rules import check_rules

CONTEXT = {"request": "Buy my dad a blood pressure monitor.", "protectedPerson": "Dad", "rules": STANDARD_RULES}


def find_offer(offer_id):
    return next(offer for offer in OFFERS if offer["id"] == offer_id)


class ScriptedAI:
    """A fake AI that returns the replies we give it, in order, and reports token usage."""
    kind = "live"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, messages, model, max_tokens=800):
        self.calls = self.calls + 1
        text = self.replies.pop(0) if self.replies else "no idea"
        return text, {"input": 1000, "output": 100}


class BrokenAI:
    kind = "live"

    def complete(self, system, messages, model, max_tokens=800):
        raise TimeoutError("the model timed out")


# ---------- offline analyzers ----------
def test_offline_reader_finds_the_hidden_renewal():
    facts = extract_facts(find_offer("bp-quickcare"), None, CaseMetrics())
    assert facts["mode"] == "offline"
    assert facts["totalDueToday"] == 4.99
    assert facts["recurring"] == {"amount": 79.0, "interval": "month"}
    assert facts["returnCost"] == 32.3          # 15% of $129 + $12.95 shipping
    assert facts["evidence"]["recurring"] == ["E4"]


def test_offline_prosecutor_catches_an_unsupported_claim():
    offer = find_offer("bp-pulseright")
    facts = extract_facts(offer, None, CaseMetrics())
    case = prosecute(offer, facts, CONTEXT, None, CaseMetrics(), quick=True)
    critical = [point for point in case["arguments"] if point["severity"] == "critical"]
    assert len(critical) == 1 and critical[0]["evidence"] == ["E1", "E4"]


def test_shopper_uses_code_not_ai_by_default():
    pick = shopper_pick("monitor", [find_offer("bp-medmart"), find_offer("bp-quickcare")], ScriptedAI([]), CaseMetrics())
    assert pick["offerId"] == "bp-quickcare" and pick["mode"] == "code"


# ---------- live path, with fake models ----------
def test_live_reply_is_checked_and_fake_citations_removed():
    reply = json.dumps({"totalDueToday": 4.99, "recurring": {"amount": 79, "interval": "month"}, "returnCost": 32.3,
                        "hiddenFees": [], "evidence": {"recurring": ["E4", "E99"]}})
    metrics = CaseMetrics()
    facts = extract_facts(find_offer("bp-quickcare"), ScriptedAI([reply]), metrics)
    assert facts["mode"] == "live" and facts["evidence"]["recurring"] == ["E4"]
    assert metrics.summary()["inputTokens"] == 1000          # usage is recorded


def test_bad_reply_gets_one_retry_then_works():
    good = json.dumps({"arguments": [{"point": "Renews monthly", "severity": "critical", "evidence": ["E4"]}]})
    ai = ScriptedAI(['{"arguments": "not a list"}', good])
    offer = find_offer("bp-quickcare")
    case = prosecute(offer, extract_facts(offer, None, CaseMetrics()), CONTEXT, ai, CaseMetrics())
    assert case["mode"] == "live" and ai.calls == 2


def test_two_bad_replies_fall_back_to_offline():
    offer = find_offer("bp-quickcare")
    metrics = CaseMetrics()
    case = prosecute(offer, extract_facts(offer, None, CaseMetrics()), CONTEXT, ScriptedAI(["hello", "still no json"]), metrics)
    assert case["mode"] == "offline" and "invalid after retry" in case["fallbackReason"]
    assert metrics.summary()["fallbacks"] == 1


def test_api_error_falls_back_to_offline():
    offer = find_offer("bp-quickcare")
    case = defend(offer, extract_facts(offer, None, CaseMetrics()), CONTEXT, BrokenAI(), CaseMetrics())
    assert case["mode"] == "offline" and "timed out" in case["fallbackReason"]


def test_points_with_fake_evidence_are_dropped():
    reply = json.dumps({"arguments": [
        {"point": "Real issue", "severity": "major", "evidence": ["E4"]},
        {"point": "Made up", "severity": "critical", "evidence": ["E42"]},
    ]})
    offer = find_offer("bp-quickcare")
    case = prosecute(offer, extract_facts(offer, None, CaseMetrics()), CONTEXT, ScriptedAI([reply]), CaseMetrics())
    assert [point["point"] for point in case["arguments"]] == ["Real issue"] and case["dropped"] == 1


def test_judge_cannot_approve_past_a_failed_rule():
    offer = find_offer("bp-quickcare")
    facts = extract_facts(offer, None, CaseMetrics())
    approve = json.dumps({"verdict": "APPROVE", "reasoning": "Looks fine.", "keyFindings": []})
    ruling = judge(offer, facts, CONTEXT, {"arguments": []}, {"arguments": []}, check_rules(facts, STANDARD_RULES),
                   ScriptedAI([approve]), CaseMetrics())
    assert ruling["verdict"] == "REJECT" and ruling["overruled"].startswith("Overruled by code")


def test_mock_mode_counts_calls_and_waits():
    settings.mock_latency_s = 0.05
    metrics = CaseMetrics()
    facts = extract_facts(find_offer("bp-medmart"), MockClient(), metrics)
    summary = metrics.summary()
    assert facts["mode"] == "mock" and summary["aiCalls"] == 1 and metrics.calls[0]["seconds"] >= 0.05


def test_extract_json_handles_extra_words_and_braces_in_strings():
    text = '<think>{"not": "this"}</think>Sure!\n```json\n{"point": "costs {a lot}", "n": 1}\n```'
    assert extract_json(text) == {"point": "costs {a lot}", "n": 1}


def test_real_ai_client_sends_the_right_request(monkeypatch):
    """Runs the REAL Anthropic client code against a fake API, so we know it is wired right before using a key."""
    from backend import llm
    sent = {}

    def fake_api(url, method="POST", headers=None, body=None, raw_body=None, timeout=60):
        sent.update(url=url, headers=headers, body=body, timeout=timeout)
        reply = {"totalDueToday": 4.99, "recurring": {"amount": 79, "interval": "month"}, "returnCost": 32.3,
                 "hiddenFees": [], "evidence": {"recurring": ["E4"]}}
        return 200, {"content": [{"type": "text", "text": json.dumps(reply)}], "usage": {"input_tokens": 812, "output_tokens": 95}}

    monkeypatch.setattr(llm, "request_json", fake_api)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    metrics = CaseMetrics()
    facts = extract_facts(find_offer("bp-quickcare"), llm.AnthropicClient(), metrics)

    assert sent["url"] == "https://api.anthropic.com/v1/messages"
    assert sent["headers"]["x-api-key"] == "test-key" and sent["headers"]["anthropic-version"] == "2023-06-01"
    assert sent["body"]["model"] == settings.fast_model and sent["timeout"] == settings.ai_timeout_s
    assert facts["mode"] == "live" and facts["recurring"]["amount"] == 79
    assert metrics.calls[0]["inputTokens"] == 812 and metrics.calls[0]["outputTokens"] == 95


def test_safety_net_catches_a_trap_the_ai_missed():
    """The AI says 'no renewal', but the fine print says otherwise: the pattern checker adds it back."""
    missed = json.dumps({"totalDueToday": 4.99, "recurring": None, "returnCost": 0, "hiddenFees": [], "evidence": {}})
    facts = extract_facts(find_offer("bp-quickcare"), ScriptedAI([missed]), CaseMetrics())
    assert facts["mode"] == "live"
    assert facts["recurring"] == {"amount": 79.0, "interval": "month"}
    assert facts["returnCost"] == 32.3
    assert facts["safetyNet"] == ["renewal", "return cost"]
