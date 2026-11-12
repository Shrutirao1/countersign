# ⚖ Countersign

**Your AI agent signs. Countersign checks the deal before PayPal pays.**

When an AI shopping agent tries to spend someone's money, PayPal holds the funds. Clear-cut traps are rejected by code in milliseconds. Only real gray areas go to an AI trial, where a prosecutor and a defense argue with cited evidence and a judge decides. PayPal captures the exact approved amount, or voids the hold if nothing passes. Every case leaves a tamper-evident receipt.

Built for the PayPal AI Hackathon 2026.

## Why it matters

Payment networks have spent the last year building ways for AI agents to pay. Those systems answer *"is this agent allowed to pay?"*. Countersign answers the next question: *"is this a good deal for the person paying?"* A naive agent that picks the cheapest price falls for $4.99 trials that renew at $79 a month, fees that appear at checkout, and "free returns" that cost $32.

## How it works

```
Guardian sets rules ──► PayPal AUTHORIZE: hold up to the budget, no money moves
         │
         ▼
Risk score for every offer (code, instant)
         │
Read the fine print of every risky offer at once (AI, parallel, cached by text hash)
         │
For each offer, cheapest first:
   verified merchant, low risk ──► code checks rules ──► approve (no AI)
   a hard rule fails ───────────► REJECT by code (no AI, no trial)
   rules pass, medium risk ─────► one quick AI check ──► nothing critical: approve
   rules pass, critical issue ──► TRIAL: prosecutor + defense (parallel) ──► judge
         │
APPROVE ──► PayPal CAPTURE exact amount, release the rest
none    ──► PayPal VOID, nothing charged
         │
Counterfactual (what a naive agent would pay) + metrics + hash-chained receipt
```

- **Hard rules are code.** The judge can never approve past a failed rule.
- **Every AI point must cite evidence.** Citations to lines that don't exist are removed; points left with none are dropped.
- **AI replies are validated** with pydantic, retried once with the error, then replaced by a labeled offline analyzer. A case always finishes.
- **Safety net.** The AI's reading of the fine print is combined with a free pattern checker, keeping the more cautious value. The AI can never miss a trap that pattern matching would catch, at no extra AI cost.

## Results

### Speed and cost: old design vs new design

Measured with `python -m evals.benchmark --live` (real AI calls). Same verdicts in both designs.

| Scenario | Run | Old: AI calls | Old: seconds | New: AI calls | New: seconds |
|---|---|---|---|---|---|
| Dad's blood pressure monitor | first | 14 | 46.2 | 6 | 19.9 |
| Dad's blood pressure monitor | repeat (cache) | 14 | 45.6 | 3 | 13.1 |
| Reorder AA batteries | first | 1 | 3.3 | 0 | 0.0 |
| Cheap dinner delivery | first | 10 | 32.3 | 2 | 3.0 |
| Cheap dinner delivery | repeat (cache) | 10 | 27.0 | 0 | 0.0 |

### Accuracy: 40 labeled offers

20 offers to tune on (dev), 20 held out (test). Bar to ship: **0 traps approved on the test split.**

| Configuration | Split | Accuracy | Traps approved | Good offers blocked | Field accuracy |
|---|---|---|---|---|---|
| Offline analyzer (no AI, baseline) | dev | 75% | 4 | 1 | 91% |
| Offline analyzer (no AI, baseline) | test | 80% | 3 | 1 | 94% |
| AI, mixed models | dev (20 × 3) | 100% | 0 | 0 | 99% |
| AI, mixed models | test, run 1 (20 × 3) | 95% | 1 | 0 | 99.6% |
| AI, mixed models | test, run 2 (20 × 3) | 100% | 0 | 0 | 98% |

With perfect fine-print reading, the decision logic scores 100% on all 40 offers (0 traps approved, 0 good offers blocked), so accuracy depends only on how well the AI reads. The baseline misses reworded subscription traps ("billed $14.99 monthly", "membership continues at $15 a month"). That gap is what the AI has to close. The full scoreboard is in `evals/report.md` and the app's Evaluation tab.

## Run it

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m pytest                       # 46 tests
python -m backend.server               # open http://localhost:3000
```

No keys: PayPal is simulated and the agents run offline. Set `AI_MODE=mock` to see AI call counts without a key. Add keys to `.env` (copy `.env.example`) for the PayPal sandbox and the real AI, and check them with `python -m backend.smoke_paypal` and `python -m backend.smoke_llm`.

## PayPal APIs used

| Step | API |
|---|---|
| Spending mandate | `POST /v2/checkout/orders` with `intent: "AUTHORIZE"` |
| Hold after buyer approval | `POST /v2/checkout/orders/{id}/authorize` |
| Approved | `POST /v2/payments/authorizations/{id}/capture` with `final_capture: true` |
| Nothing passed | `POST /v2/payments/authorizations/{id}/void` |

## Proof

See `docs/proof/`: receipts from live sandbox runs, PayPal's records of the same IDs, and both smoke tests.

## License

MIT

