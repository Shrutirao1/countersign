"""End to end over HTTP: start the real server and use it like the browser does."""
import json
import urllib.error
import urllib.request

import pytest

from backend.server import start_in_background

RULES = {"budget": 100, "noSubscriptions": True, "requireFreeReturns": True, "noHiddenFees": True}


@pytest.fixture
def base_url():
    server = start_in_background(0)       # port 0 = any free port
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def call(base_url, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    method = "POST" if data else "GET"
    request = urllib.request.Request(base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def run_dad_case(base_url):
    status, order = call(base_url, "/api/mandate", {"scenarioId": "dad_bp", "rules": RULES})
    status, text = call(base_url, "/api/run", {"orderId": json.loads(order)["id"], "scenarioId": "dad_bp", "rules": RULES})
    return [json.loads(line) for line in text.splitlines()]


def test_config_reports_modes_and_switches(base_url):
    status, text = call(base_url, "/api/config")
    config = json.loads(text)
    assert status == 200 and config["paypalMode"] == "simulated" and config["aiMode"] == "offline"
    assert config["flags"]["skipTrialOnRuleFail"] is True


def test_full_case_streams_then_receipt_stats_and_verify_work(base_url):
    events = run_dad_case(base_url)
    assert events[0]["type"] == "hold" and events[-1]["type"] == "done"
    receipt_id = next(event for event in events if event["type"] == "receipt")["id"]

    status, text = call(base_url, f"/api/receipts/{receipt_id}")
    assert status == 200 and json.loads(text)["body"]["payment"]["amount"] == 52.0
    assert json.loads(call(base_url, "/api/receipts/verify")[1])["ok"] is True
    stats = json.loads(call(base_url, "/api/stats")[1])
    assert stats["cases"] == 1 and stats["approvedSpend"] == 52.0 and stats["blockedFirstYear"] == 900.99


def test_eval_route_returns_results(base_url):
    status, text = call(base_url, "/api/eval")
    assert status == 200 and "runs" in json.loads(text)


def test_bad_budget_gets_a_clear_400(base_url):
    status, text = call(base_url, "/api/mandate", {"scenarioId": "dad_bp", "rules": {"budget": -5}})
    assert status == 400 and "budget" in json.loads(text)["error"]


def test_serves_the_app_but_nothing_outside_frontend(base_url):
    assert call(base_url, "/")[0] == 200
    assert call(base_url, "/app.js")[0] == 200
    assert call(base_url, "/../backend/config.py")[0] == 404
