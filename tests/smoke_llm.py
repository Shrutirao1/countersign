"""
smoke_llm.py - prove the real AI agents work with your key.

    python -m backend.smoke_llm

Runs the fine-print reader and the quick check on the $4.99 trap and prints
mode, tokens and seconds for each. mode must say "live". If it says
"offline", the AI call failed and the reason is printed.
"""
from .agents import extract_facts, prosecute
from .catalog import OFFERS, STANDARD_RULES
from .config import settings
from .llm import AnthropicClient
from .metrics import CaseMetrics

if not settings.anthropic_api_key:
    raise SystemExit("ANTHROPIC_API_KEY is empty. Put your key in the .env file.")

client = AnthropicClient()
metrics = CaseMetrics()
offer = next(item for item in OFFERS if item["id"] == "bp-quickcare")
context = {"request": "Buy my dad a blood pressure monitor.", "protectedPerson": "Dad", "rules": STANDARD_RULES}

print(f"1) Fine-print reader ({settings.fast_model}) on the $4.99 offer")
facts = extract_facts(offer, client, metrics)
print(f"     mode={facts['mode']}  due today=${facts['totalDueToday']}  recurring={facts['recurring']}  return cost={facts['returnCost']}")
if facts.get("fallbackReason"):
    print("     reason:", facts["fallbackReason"])

print("\n2) Quick check")
case = prosecute(offer, facts, context, client, metrics, quick=True)
for point in case["arguments"]:
    print(f"     [{point['severity']}] {point['point']}  {point['evidence']}")
print(f"     mode={case['mode']}  points dropped for fake evidence={case['dropped']}")

print("\n3) Measured")
for call in metrics.calls:
    print(f"     {call['agent']:<12} {call['inputTokens']:>5} in / {call['outputTokens']:>4} out tokens  {call['seconds']:.1f} s  ${call['cost']:.5f}")

ok = facts["mode"] == "live" and case["mode"] == "live" and facts["recurring"] is not None
if ok:
    print("\nReady!")
else:
    print("\nNot ready: see the mode and reason above.")
