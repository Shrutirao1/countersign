"""PayPal: the simulation's rules, and the real-API code path against a fake PayPal."""
import pytest

from backend import paypal_client as paypal


def test_runs_simulated_without_keys():
    assert paypal.settings.paypal_mode == "simulated"


def test_hold_then_capture_less_than_the_hold():
    order = paypal.create_mandate_order(100, "test")
    auth = paypal.authorize_order(order["id"])
    capture = paypal.capture_authorization(auth["authorizationId"], 52.0)
    assert auth["amount"] == 100
    assert capture["status"] == "COMPLETED" and capture["amount"] == 52.0


def test_cannot_capture_more_than_the_hold():
    auth = paypal.authorize_order(paypal.create_mandate_order(50, "test")["id"])
    with pytest.raises(RuntimeError, match="exceeds"):
        paypal.capture_authorization(auth["authorizationId"], 50.01)


def test_void_releases_the_hold_and_blocks_capture():
    auth = paypal.authorize_order(paypal.create_mandate_order(50, "test")["id"])
    assert paypal.void_authorization(auth["authorizationId"])["status"] == "VOIDED"
    with pytest.raises(RuntimeError):
        paypal.capture_authorization(auth["authorizationId"], 1)


def test_order_can_only_be_authorized_once():
    order = paypal.create_mandate_order(20, "test")
    paypal.authorize_order(order["id"])
    with pytest.raises(RuntimeError):
        paypal.authorize_order(order["id"])


def test_sandbox_code_calls_the_right_paypal_endpoints(monkeypatch):
    """Runs the REAL sandbox code against a fake PayPal, so we know it is wired right before using keys."""
    calls = []

    def fake_paypal(url, method="POST", headers=None, body=None, raw_body=None, timeout=60):
        calls.append((url.split(".paypal.com")[1], body))
        if url.endswith("/v1/oauth2/token"):
            return 200, {"access_token": "TOKEN", "expires_in": 3600}
        if url.endswith("/v2/checkout/orders"):
            return 201, {"id": "ORDER1", "status": "CREATED", "links": [{"rel": "approve", "href": "https://paypal.test/approve"}]}
        if url.endswith("/authorize"):
            return 201, {"purchase_units": [{"payments": {"authorizations": [{"id": "AUTH1", "status": "CREATED", "amount": {"value": "100.00"}}]}}]}
        if url.endswith("/capture"):
            return 201, {"id": "CAP1", "status": "COMPLETED", "amount": {"value": "52.00"}}
        return 204, {}

    monkeypatch.setattr(paypal.settings, "paypal_client_id", "id")
    monkeypatch.setattr(paypal.settings, "paypal_client_secret", "secret")
    monkeypatch.setattr(paypal, "request_json", fake_paypal)
    monkeypatch.setitem(paypal.saved_token, "value", None)

    order = paypal.create_mandate_order(100, "Dad's monitor")
    auth = paypal.authorize_order(order["id"])
    capture = paypal.capture_authorization(auth["authorizationId"], 52)
    paypal.void_authorization("AUTH2")

    assert order["approveUrl"] == "https://paypal.test/approve"
    assert capture["amount"] == 52.0
    paths = [path for path, body in calls]
    assert paths == ["/v1/oauth2/token", "/v2/checkout/orders", "/v2/checkout/orders/ORDER1/authorize",
                     "/v2/payments/authorizations/AUTH1/capture", "/v2/payments/authorizations/AUTH2/void"]
    assert calls[1][1]["intent"] == "AUTHORIZE"
    assert calls[3][1]["amount"]["value"] == "52.00" and calls[3][1]["final_capture"] is True
