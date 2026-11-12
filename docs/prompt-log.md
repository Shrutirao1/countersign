# Prompt log

Every prompt change, measured on the **dev** split only (20 offers).
The test split stays untouched until the prompts are frozen.

| Date | What changed | Accuracy | Traps approved | Good offers blocked | Field accuracy | Median s | Cost/offer |
|---|---|---|---|---|---|---|---|
| Nov 12 | First live run (no prompt changes) | 95% | 1 (g03) | 0 | 100% | 3.6 | $0.0013 |
| Nov 12 | Prosecutor: a product-page claim the fine print takes back or limits is always critical | 100% | 0 | 0 | 98% | 3.9 | $0.0016 |
| Nov 12 | Same prompts, re-run to check stability | 100% | 0 | 0 | 96% | 3.5 | $0.0016 |

## What g03 was
The product page promised a "lifetime warranty". The fine print limited it to 90 days.
The quick check called it minor, so the offer was approved. After the fix it is flagged critical, goes to trial, and is rejected.

## Freeze
Prompts frozen on Nov 12 after the rows above. The test split is run once, after this commit.