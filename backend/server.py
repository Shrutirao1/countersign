"""
server.py - the web server: the API plus the web app in frontend/.

Start it:   python -m backend.server      then open http://localhost:3000

API routes
    GET  /api/config               modes (PayPal, AI), switches and the demo scenarios
    POST /api/mandate              create the PayPal hold (AUTHORIZE order) for the budget
    POST /api/run                  place the hold, run the case, stream every step
    GET  /api/receipts             list of saved receipts
    GET  /api/receipts/verify      re-check the whole hash chain
    GET  /api/receipts/<id>        one full receipt
    GET  /api/stats                totals for the Dashboard tab
    GET  /api/eval                 evaluation and benchmark results for the Evaluation tab
    GET  /api/precedents           case law
    POST /api/demo/reset           clear case law and the facts cache before a demo

It uses Python's built-in http.server, so there is nothing extra to install.
"""
import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pydantic import ValidationError

from .catalog import SCENARIOS, get_scenario
from .config import ROOT, settings
from .facts_cache import clear_cache
from .llm import make_client
from .paypal_client import authorize_order, create_mandate_order
from .precedents import all_precedents, reset_precedents
from .receipts import get_receipt, load_receipts, verify_chain
from .schemas import MandateRequest, RunRequest
from .stats import dashboard_stats
from .trial import run_case

FRONTEND = ROOT / "frontend"
RESULTS = ROOT / "evals" / "results"
mimetypes.add_type("text/javascript", ".js")


class BadRequest(Exception):
    """The browser sent something invalid. We answer with status 400."""


def validate(model_class, body):
    """Check the request body with a pydantic model, or raise BadRequest with a clear message."""
    try:
        return model_class.model_validate(body)
    except ValidationError as err:
        first = err.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise BadRequest(f"{where}: {first['msg']}") from None


# ---------------------------------------------------------------
# Route handlers. Each one gets the request body and returns a dict.
# ---------------------------------------------------------------
def route_config(body):
    return {
        "paypalMode": settings.paypal_mode,
        "paypalClientId": settings.paypal_client_id,
        "aiMode": settings.llm_mode,
        "fastModel": settings.fast_model,
        "judgeModel": settings.judge_model,
        "flags": settings.efficiency_flags(),
        "scenarios": SCENARIOS,
    }


def route_mandate(body):
    request = validate(MandateRequest, body)
    scenario = get_scenario(request.scenarioId)
    if not scenario:
        raise BadRequest(f"Unknown scenario {request.scenarioId!r}")
    return create_mandate_order(request.rules.budget, f"Countersign mandate: {scenario['request']}")


def route_receipts(body):
    """A short list of receipts, newest first."""
    items = []
    for receipt in reversed(load_receipts()):
        items.append({
            "id": receipt["id"],
            "createdAt": receipt["createdAt"],
            "hash": receipt["hash"],
            "previousHash": receipt["previousHash"],
            "request": receipt["body"]["request"],
            "outcome": receipt["body"]["outcome"],
            "amount": receipt["body"]["payment"]["amount"],
            "paypalMode": receipt["body"]["payment"]["paypalMode"],
            "aiMode": receipt["body"]["aiMode"],
        })
    return items


def route_verify(body):
    return verify_chain()


def route_stats(body):
    return dashboard_stats()


def route_eval(body):
    """Every results file the evaluation runner and the benchmark have written."""
    runs = []
    benchmark = None
    if RESULTS.exists():
        for path in sorted(RESULTS.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if path.name == "benchmark.json":
                benchmark = data
            else:
                runs.append(data)
    return {"runs": runs, "benchmark": benchmark}


def route_precedents(body):
    return all_precedents()


def route_reset(body):
    reset_precedents()
    clear_cache()
    return {"ok": True}


ROUTES = {
    ("GET", "/api/config"): route_config,
    ("POST", "/api/mandate"): route_mandate,
    ("GET", "/api/receipts"): route_receipts,
    ("GET", "/api/receipts/verify"): route_verify,
    ("GET", "/api/stats"): route_stats,
    ("GET", "/api/eval"): route_eval,
    ("GET", "/api/precedents"): route_precedents,
    ("POST", "/api/demo/reset"): route_reset,
}


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 ends the response when the connection closes, which lets /api/run stream.
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def handle_request(self, method):
        path = urlparse(self.path).path

        # The one streaming route.
        if method == "POST" and path == "/api/run":
            return self.run_route(self.read_body())

        # One full receipt: /api/receipts/CS-0001
        if method == "GET" and path.startswith("/api/receipts/CS-"):
            receipt = get_receipt(path.split("/")[-1])
            if receipt is None:
                return self.send_json(404, {"error": "No such receipt"})
            return self.send_json(200, receipt)

        handler = ROUTES.get((method, path))
        if handler is None:
            return self.serve_file(path)
        try:
            if method == "POST":
                body = self.read_body()
            else:
                body = {}
            self.send_json(200, handler(body))
        except BadRequest as err:
            self.send_json(400, {"error": str(err)})
        except Exception as err:
            traceback.print_exc()
            self.send_json(500, {"error": str(err)})

    def run_route(self, body):
        """Place the hold, run the case, and stream one JSON event per line."""
        try:
            request = validate(RunRequest, body)
        except BadRequest as err:
            return self.send_json(400, {"error": str(err)})

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event):
            self.wfile.write((json.dumps(event) + "\n").encode())
            self.wfile.flush()

        try:
            authorization = authorize_order(request.orderId)
            run_case(request.scenarioId, request.rules.model_dump(), authorization, emit,
                     client=make_client(), order_id=request.orderId)
            emit({"type": "done"})
        except Exception as err:
            traceback.print_exc()
            emit({"type": "error", "message": str(err)})

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def send_json(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_file(self, path):
        """Serve a file from frontend/ (index.html for '/'). Nothing outside that folder."""
        if path == "/":
            path = "/index.html"
        file = (FRONTEND / path.lstrip("/")).resolve()
        if FRONTEND not in file.parents or not file.is_file():
            return self.send_json(404, {"error": "Not found"})
        data = file.read_bytes()
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"):
            content_type = content_type + "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Only print API requests, not every file.
        if args and "/api/" in str(args[0]):
            super().log_message(format, *args)


def start_in_background(port=0):
    """For tests: start the server on a free port in a background thread."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    server = ThreadingHTTPServer(("127.0.0.1", settings.port), Handler)
    print(f"Countersign running at http://localhost:{settings.port}")
    print(f"  PayPal: {settings.paypal_mode}   AI agents: {settings.llm_mode}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
