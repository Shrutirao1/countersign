"""
smoke_paypal.py - prove the PayPal sandbox works with your keys. Two runs:

  python -m backend.smoke_paypal
      gets a token, creates a $5.00 AUTHORIZE order, prints the approval link.
      Open the link, log in as your sandbox *Personal* (buyer) account, approve.

  python -m backend.smoke_paypal <ORDER_ID>
      places the hold, captures $1.00 and releases the rest.
      Add --void at the end to release the whole hold instead.
"""
import sys

from .config import settings
from .paypal_client import access_token, authorize_order, capture_authorization, create_mandate_order, void_authorization

if settings.paypal_mode != "sandbox":
    raise SystemExit("PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET is empty. Put your sandbox keys in the .env file.")

order_ids = [arg for arg in sys.argv[1:] if not arg.startswith("--")]

if not order_ids:
    print("1) Access token:", access_token()[:12] + "...  (OK)")
    order = create_mandate_order(5.00, "Countersign smoke test")
    print(f"2) Created order {order['id']}  status={order['status']}")
    print(f"3) Approve it as your sandbox buyer:\n     {order['approveUrl']}")
    print(f"4) Then run:  python -m backend.smoke_paypal {order['id']}")
else:
    auth = authorize_order(order_ids[0])
    print(f"1) Hold placed: {auth['authorizationId']}  ${auth['amount']:.2f}  status={auth['status']}")
    if "--void" in sys.argv:
        print("2) Voided:", void_authorization(auth["authorizationId"])["status"])
    else:
        capture = capture_authorization(auth["authorizationId"], 1.00, "Countersign smoke test")
        print(f"2) Captured ${capture['amount']:.2f}  {capture['captureId']}  status={capture['status']}  (rest of the hold released)")
    print("\nReady! Check Testing Tools > Sandbox Accounts > your Business account > Activity on developer.paypal.com.")
