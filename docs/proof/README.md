# Proof pack

Evidence that Countersign works end to end with the real PayPal sandbox and the real AI.

| File | What it proves | How to make it |
|---|---|---|
| `receipt-capture.json` | A real sandbox case that captured money | Run Dad's monitor with your keys, then copy `data/receipts/<number>.json` here |
| `receipt-void.json` | A real sandbox case that voided the hold | Run the dinner-delivery case, then copy its receipt here |
| `paypal-capture.png` | PayPal's own record of the same capture ID | Screenshot of the sandbox account activity |
| `paypal-void.png` | PayPal's own record of the void | Same, for the voided authorization |
| `smoke-paypal.png`, `smoke-llm.png` | The two smoke tests ending in "Ready!" | Screenshot the terminal |
| `chain-verified.png` | The receipt chain is intact | Receipts tab > Verify chain |

The authorization and capture IDs in each receipt must match the IDs in PayPal's screenshots.
