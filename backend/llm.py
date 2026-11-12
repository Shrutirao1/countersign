"""
llm.py - how we talk to the AI model.

AnthropicClient  -> the real model (Anthropic Messages API)
MockClient       -> no real AI: the agents use their offline answers, plus a fake
                    delay, so you can test speed and call counts without a key
make_client()    -> picks one based on settings.llm_mode (None means offline)

ask() sends one request, finds the JSON in the reply, checks it with a pydantic
model, and if the reply is bad it tries ONE more time and tells the model what
was wrong. It returns (parsed_reply, token_usage).
"""
import json
import re

from pydantic import ValidationError

from .config import settings
from .http_util import request_json


class LLMReplyError(ValueError):
    """The model's reply was not valid JSON for what we asked."""


class AnthropicClient:
    kind = "live"

    def complete(self, system, messages, model, max_tokens=800):
        """Send one request. Returns (reply_text, {"input": tokens, "output": tokens})."""
        status, data = request_json(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            body={"model": model, "max_tokens": max_tokens, "system": system, "messages": messages},
            timeout=settings.ai_timeout_s,   # a slow call fails fast, then the offline analyzer takes over
        )
        text = ""
        for part in data.get("content", []):
            text = text + part.get("text", "")
        usage = data.get("usage", {})   # the API tells us exactly how many tokens it used
        return text, {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}


class MockClient:
    """Pretends to be the AI. The agents notice kind == 'mock' and use offline answers with a delay."""
    kind = "mock"


def make_client():
    """The AI client for the current mode, or None for offline."""
    if settings.llm_mode == "live":
        return AnthropicClient()
    if settings.llm_mode == "mock":
        return MockClient()
    return None


def extract_json(text):
    """
    Find the first complete {...} JSON object in the model's reply.
    Models sometimes add words or ```json fences around the JSON, so we search for it.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)   # drop any thinking notes
    start = text.find("{")
    while start != -1:
        depth = 0
        inside_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if inside_string:            # braces inside "strings" don't count
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    inside_string = False
                continue
            if char == '"':
                inside_string = True
            elif char == "{":
                depth = depth + 1
            elif char == "}":
                depth = depth - 1
                if depth == 0:
                    try:
                        return json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise LLMReplyError("no JSON object found in the reply")


def ask(client, model_class, system, user, model, max_tokens=800):
    """
    Ask the model and get back a checked reply.

    Returns (reply, usage). reply is an instance of model_class.
    Raises LLMReplyError if the reply is still bad after one retry.
    """
    system = system + "\n\nReply with ONE JSON object and nothing else."
    messages = [{"role": "user", "content": user}]
    usage = {"input": 0, "output": 0}
    problem = ""

    for attempt in (1, 2):   # first try + one retry
        text, used = client.complete(system, messages, model, max_tokens)
        usage["input"] = usage["input"] + used["input"]
        usage["output"] = usage["output"] + used["output"]
        try:
            reply = model_class.model_validate(extract_json(text))
            return reply, usage
        except LLMReplyError as err:
            problem = str(err)
        except ValidationError as err:
            first = err.errors()[0]
            problem = f"field {first['loc']}: {first['msg']}"
        # Show the model its bad reply and what was wrong, then try again.
        messages.append({"role": "assistant", "content": text[:2000] or "(empty)"})
        messages.append({"role": "user", "content": f"That reply was invalid: {problem}. Reply with one corrected JSON object only."})

    raise LLMReplyError(f"invalid after retry: {problem}")
