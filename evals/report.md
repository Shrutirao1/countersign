# Countersign evaluation

## Scoreboard

| Configuration | Split | Offers x repeats | Accuracy | Traps approved | Good offers blocked | Field accuracy | Fallback rate | Median s | Slowest 5% s | AI calls / offer | Cost / offer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mixed | dev | 20 x 3 | 100% | 0 | 0 | 99% | 0% | 3.89 | 11.98 | 1.9 | $0.0016 |
| mixed | test | 20 x 3 | 100% | 0 | 0 | 98% | 0% | 4.17 | 12.39 | 2.0 | $0.0019 |
| offline | dev | 20 x 1 | 75% | 4 | 1 | 91% | n/a | 0.00 | 0.00 | 0.0 | $0.0000 |
| offline | test | 20 x 1 | 80% | 3 | 1 | 94% | n/a | 0.00 | 0.00 | 0.0 | $0.0000 |

Bar to ship: 0 traps approved on the test split, 2 or fewer good offers blocked, field accuracy of 90% or better, fallback rate under 5%.

**offline / dev** traps approved: h03, s01, s05, s07; good offers blocked: c07

**offline / test** traps approved: s02, s04, s06; good offers blocked: c10

## Before and after the speed and cost changes

AI mode: live. Real AI calls.

| Scenario | Run | Old design: AI calls | Old design: seconds | New design: AI calls | New design: seconds |
| --- | --- | --- | --- | --- | --- |
| Dad's blood pressure monitor | first run | 14 | 46.20 | 6 | 19.92 |
| Dad's blood pressure monitor | repeat run | 14 | 45.59 | 3 | 13.11 |
| Reorder AA batteries | first run | 1 | 3.31 | 0 | 0.00 |
| Reorder AA batteries | repeat run | 1 | 1.96 | 0 | 0.00 |
| Cheap dinner delivery | first run | 10 | 32.29 | 2 | 2.96 |
| Cheap dinner delivery | repeat run | 10 | 27.04 | 0 | 0.00 |

