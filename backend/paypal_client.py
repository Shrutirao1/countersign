"""
paypal_client.py - every call to PayPal lives here.

The idea: the guardian approves ONE hold for "up to the budget".
No money moves until a purchase wins its case.

    create_mandate_order  -> make a PayPal order with intent AUTHORIZE
    authorize_order       -> after the buyer approves: place the hold
    capture_authorization -> verdict APPROVE: take only the approved amount
    void_authorization    -> nothing passed: release the hold, nothing charged

Without PayPal keys this file runs a simulation with the same rules
(you can't take more than the hold, or capture twice), so the demo always works.
"""
import base64
import random
import string
import time

from .config import settings
from .http_util import request_json


def money(amount):
    """PayPal wants amounts as text with 2 decimals, like '52.00'."""
    return f"{float(amount):.2f}"


# ---------------------------------------------------------------
# Talking to the real PayPal sandbox
# ---------------------------------------------------------------
# PayPal gives us an access token that lasts a few hours. We keep it here.
saved_token = {"value": None, "expires": 0.0}


def access_token():
    """Get a PayPal access token (reuse the saved one while it is still valid)."""
    if saved_token["value"] and saved_token["expires"] > time.time():
        return saved_token["value"]

    login = f"{settings.paypal_client_id}:{settings.paypal_client_secret}"
    basic = base64.b64encode(login.encode()).decode()
    status, data = request_json(
        f"{settings.paypal_base_url}/v1/oauth2/token",
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        raw_body=b"grant_type=client_credentials",
    )
    saved_token["value"] = data["access_token"]
    # Refresh one minute early to be safe.
    saved_token["expires"] = time.time() + data["expires_in"] - 60
    return saved_token["value"]


def call_paypal(path, body=None):
    """POST to a PayPal API path and return the JSON reply."""
    if body is None:
        body = {}
    status, data = request_json(
        f"{settings.paypal_base_url}{path}",
        headers={
            "Authorization": f"Bearer {access_token()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
        body=body,
    )
    return data


# ---------------------------------------------------------------
# The simulation (used when there are no PayPal keys)
# ---------------------------------------------------------------
SIM = {}   # id -> {"status": ..., "amount": ...}


def fake_id(prefix):
    letters = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{letters}"


# ---------------------------------------------------------------
# The four PayPal actions
# ---------------------------------------------------------------
def create_mandate_order(budget, description):
    """Step 1: make an order for 'up to the budget' with intent AUTHORIZE."""
    if settings.paypal_mode == "simulated":
        order_id = fake_id("SIMORDER")
        SIM[order_id] = {"status": "CREATED", "amount": float(budget)}
        return {"id": order_id, "status": "CREATED", "approveUrl": None}

    data = call_paypal("/v2/checkout/orders", {
        "intent": "AUTHORIZE",
        "purchase_units": [{
            "description": description[:120],
            "amount": {"currency_code": "USD", "value": money(budget)},
        }],
    })
    # PayPal sends back a link where the buyer approves the order.
    approve_url = None
    for link in data.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            approve_url = link["href"]
    return {"id": data["id"], "status": data["status"], "approveUrl": approve_url}


def authorize_order(order_id):
    """Step 2: the buyer approved, so place the hold. No money moves yet."""
    if settings.paypal_mode == "simulated":
        order = SIM.get(order_id)
        if not order or order["status"] != "CREATED":
            raise RuntimeError(f"Order {order_id} is unknown or already authorized")
        auth_id = fake_id("SIMAUTH")
        order["status"] = "AUTHORIZED"
        SIM[auth_id] = {"status": "CREATED", "amount": order["amount"]}
        return {"authorizationId": auth_id, "amount": order["amount"], "status": "CREATED"}

    data = call_paypal(f"/v2/checkout/orders/{order_id}/authorize")
    authorizations = data.get("purchase_units", [{}])[0].get("payments", {}).get("authorizations", [])
    if not authorizations:
        raise RuntimeError("PayPal returned no authorization")
    auth = authorizations[0]
    return {"authorizationId": auth["id"], "amount": float(auth["amount"]["value"]), "status": auth["status"]}


def capture_authorization(authorization_id, amount, note=""):
    """Verdict APPROVE: take only the approved amount. final_capture releases the rest."""
    if settings.paypal_mode == "simulated":
        auth = SIM.get(authorization_id)
        if not auth or auth["status"] != "CREATED":
            raise RuntimeError(f"Authorization {authorization_id} is unknown, captured or voided")
        if amount > auth["amount"] + 0.001:
            raise RuntimeError(f"Capture ${amount:.2f} exceeds authorized ${auth['amount']:.2f}")
        auth["status"] = "CAPTURED"
        return {"captureId": fake_id("SIMCAP"), "amount": float(amount), "status": "COMPLETED"}

    data = call_paypal(f"/v2/payments/authorizations/{authorization_id}/capture", {
        "amount": {"currency_code": "USD", "value": money(amount)},
        "final_capture": True,
        "note_to_payer": note[:255],
    })
    captured = float(data.get("amount", {}).get("value", amount))
    return {"captureId": data["id"], "amount": captured, "status": data["status"]}


def void_authorization(authorization_id):
    """Nothing passed: release the whole hold. Nothing is charged."""
    if settings.paypal_mode == "simulated":
        auth = SIM.get(authorization_id)
        if not auth or auth["status"] != "CREATED":
            raise RuntimeError(f"Authorization {authorization_id} is unknown, captured or voided")
        auth["status"] = "VOIDED"
        return {"status": "VOIDED"}

    call_paypal(f"/v2/payments/authorizations/{authorization_id}/void")
    return {"status": "VOIDED"}
