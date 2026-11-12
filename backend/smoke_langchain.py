"""
smoke_langchain.py - prove the LangChain client works with your key.

    python -m backend.smoke_langchain

Same check as smoke_llm.py, but the agents talk to the AI through LangChain.
Makes 2 small live calls (a fraction of a cent). Writes nothing to your data folder.
"""
import tempfile
from pathlib import Path

from .agents import extract_facts, prosecute
from .catalog import SCENARIOS, offers_for
from .config import settings
from .llm_langchain import LangChainClient
from .metrics import CaseMetrics

if not settings.anthropic_api_key:
    raise SystemExit("ANTHROPIC_API_KEY is empty. Put your key in the .env file.")

settings.data_dir = Path(tempfile.mkdtemp(prefix="cx-langchain-"))   # keep your real call log untouched
offer = next(o for o in offers_for("dad_bp") if o["id"] == "bp-quickcare")

client = LangChainClient()
metrics = CaseMetrics()
scenario = next(s for s in SCENARIOS if s["id"] == "dad_bp")
context = {"request": scenario["request"], "protectedPerson": scenario["protectedPerson"],
           "rules": scenario["defaultRules"]}

print(f"1) Fine-print reader via LangChain ({settings.fast_model}) on the {offer['id']} offer")
facts = extract_facts(offer, client, metrics)
print(f"     mode={facts['mode']}  due today=${facts['totalDueToday']:.2f}  "
      f"recurring={facts.get('recurring')}  return cost={facts.get('returnCost')}")

print("\n2) Quick check via LangChain")
quick = prosecute(offer, facts, context, client, metrics, quick=True)
for point in quick["arguments"]:
    print(f"     [{point['severity']}] {point['point'][:110]}")
print(f"     mode={quick['mode']}")

print("\n3) Measured")
for call in metrics.calls:
    print(f"     {call['agent']:<12} {call['inputTokens']:>5} in / {call['outputTokens']:>5} out tokens  "
          f"{call['seconds']:.1f} s")

ok = facts["mode"] == "live" and quick["mode"] == "live"
print("\nReady! LangChain client works." if ok else "\nNot ready: a call fell back to offline (see the message above).")
