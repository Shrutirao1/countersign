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

## Final test (20 held-out offers x 3 runs)

| Run | Accuracy | Traps approved | Good offers blocked | Field accuracy | Consistency | Median s | Cost/offer |
|---|---|---|---|---|---|---|---|
| No AI (baseline) | 80% | 3 | 1 | 94% | n/a | 0.0 | $0 |
| AI, blind first run | 95% | 1 (g06) | 0 | 99.6% | 100% | 4.1 | $0.0019 |
| AI, after the fix below | 100% | 0 | 0 | 98% | 100% | 4.2 | $0.0019 |

**The fix:** g06 ("certified refurbished, like new", but the certification excludes the battery) is the same kind
of trap as g03: the fine print takes back part of a promise. One general rule was added to the prosecutor and the
judge, using an example that is not g06. Dev stayed at 100% with 0 good offers blocked. The test was then re-run.
Because the fix came after seeing the blind run, both rows are shown.