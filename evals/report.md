# Countersign evaluation

## Scoreboard

| Configuration | Split | Offers x repeats | Accuracy | Traps approved | Good offers blocked | Field accuracy | Fallback rate | Median s | Slowest 5% s | AI calls / offer | Cost / offer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| offline | dev | 20 x 1 | 75% | 4 | 1 | 91% | n/a | 0.00 | 0.00 | 0.0 | $0.0000 |
| offline | test | 20 x 1 | 80% | 3 | 1 | 94% | n/a | 0.00 | 0.00 | 0.0 | $0.0000 |

Bar to ship: 0 traps approved on the test split, 2 or fewer good offers blocked, field accuracy of 90% or better, fallback rate under 5%.

**offline / dev** traps approved: h03, s01, s05, s07; good offers blocked: c07

**offline / test** traps approved: s02, s04, s06; good offers blocked: c10

## Before and after the speed and cost changes

AI mode: mock. Mock AI: every call waits 0.4 s, so seconds show the effect of running calls in parallel. Real seconds come from --live.

| Scenario | Run | Old design: AI calls | Old design: seconds | New design: AI calls | New design: seconds |
| --- | --- | --- | --- | --- | --- |
| Dad's blood pressure monitor | first run | 14 | 5.66 | 6 | 1.62 |
| Dad's blood pressure monitor | repeat run | 14 | 5.66 | 3 | 1.22 |
| Reorder AA batteries | first run | 1 | 0.41 | 0 | 0.00 |
| Reorder AA batteries | repeat run | 1 | 0.41 | 0 | 0.00 |
| Cheap dinner delivery | first run | 10 | 4.03 | 2 | 0.41 |
| Cheap dinner delivery | repeat run | 10 | 4.04 | 0 | 0.00 |

