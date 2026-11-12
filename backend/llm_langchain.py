"""
llm_langchain.py - an OPTIONAL LangChain version of the AI client.

LangChainClient has the same interface as llm.AnthropicClient (kind + complete()),
so every agent in agents.py works with it unchanged. It sends requests through
LangChain's ChatAnthropic chat model instead of the plain HTTP client.

Nothing else in the project imports this file, so the app, the tests, the
evaluation and the benchmark keep using the original client.

    pip install -r backend/requirements-langgraph.txt
    python -m backend.smoke_langchain
"""
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from .config import settings


def _to_langchain(system, messages):
    """Convert our {"role", "content"} messages into LangChain message objects."""
    converted = [SystemMessage(content=system)]
    for message in messages:
        if message["role"] == "assistant":
            converted.append(AIMessage(content=message["content"]))
        else:
            converted.append(HumanMessage(content=message["content"]))
    return converted


def _reply_text(reply):
    """LangChain may return the reply as a string or as a list of content blocks."""
    content = reply.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)


class LangChainClient:
    kind = "live"   # the agents treat it exactly like the real AI client

    def __init__(self):
        self._models = {}

    def _model(self, model, max_tokens):
        key = (model, max_tokens)
        if key not in self._models:
            self._models[key] = ChatAnthropic(
                model=model,
                max_tokens=max_tokens,
                api_key=settings.anthropic_api_key,
                timeout=settings.ai_timeout_s,
                max_retries=0,   # our own ask() already retries once with the error
            )
        return self._models[key]

    def complete(self, system, messages, model, max_tokens=800):
        """Send one request. Returns (reply_text, {"input": tokens, "output": tokens})."""
        max_tokens = max(max_tokens, 2000)   # same floor as llm.AnthropicClient
        reply = self._model(model, max_tokens).invoke(_to_langchain(system, messages))
        usage = getattr(reply, "usage_metadata", None) or {}
        return _reply_text(reply), {"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)}
