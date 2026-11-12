"""
http_util.py - a tiny helper for calling JSON web APIs (PayPal and the AI).

It uses urllib from Python's standard library, so there is nothing extra to install.
"""
import json
import urllib.error
import urllib.request


class HTTPError(RuntimeError):
    """Raised when the API answers with an error code like 400 or 500."""

    def __init__(self, status, body, url):
        super().__init__(f"{url} failed: {status} {body[:500]}")
        self.status = status
        self.body = body


def request_json(url, method="POST", headers=None, body=None, raw_body=None, timeout=60):
    """
    Send one HTTP request and return (status_code, parsed_json).

    body      -> a Python dict, sent as JSON
    raw_body  -> bytes, sent exactly as they are (PayPal's token call needs this)
    timeout   -> give up after this many seconds
    """
    # Work out what bytes to send.
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode()
    else:
        data = None

    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode()
            if text:
                return response.status, json.loads(text)
            return response.status, {}
    except urllib.error.HTTPError as err:
        error_text = err.read().decode(errors="replace")
        raise HTTPError(err.code, error_text, url) from None
