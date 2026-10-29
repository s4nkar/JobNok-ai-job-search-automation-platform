"""Unit tests for app.ai.llm.provider's chain dispatch — specifically the
429 backoff-and-retry behavior, plus stream_text's reasoning_effort/
finish_reason handling. httpx.AsyncClient.post/.stream are monkeypatched
directly (no network access); asyncio.sleep is monkeypatched to a no-op so
the retry test doesn't actually wait."""

import json

import httpx

from app.ai.llm import provider
from app.core.config import settings


def _response(status_code: int, content: str = "") -> httpx.Response:
    if status_code >= 400:
        return httpx.Response(status_code, text="rate limited")
    body = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    return httpx.Response(status_code, json=body)


def _patch_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "groq")
    monkeypatch.setattr(settings, "ai_fallback_chain", "openrouter")
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-openrouter-key")


def _patch_cache_bypass(monkeypatch):
    """Isolates _run_chain's dispatch loop from Redis/Upstash entirely.
    circuit_is_open and check_tool_budget both go out over HTTP (Upstash's
    REST API) through the exact same httpx.AsyncClient.post these tests
    monkeypatch for the LLM provider calls below — left unpatched, that real
    (or CI's placeholder) Upstash call gets intercepted by fake_post too,
    silently popping a response meant for the LLM mock and desyncing the
    whole sequence (hit live: a 3-response 429/429/200 fixture produced a
    successful result attributed to the wrong provider, because the first two
    "provider" calls fake_post saw were actually circuit_is_open checks, not
    LLM calls at all)."""
    async def _not_open(scope, provider_name):
        return False

    async def _record_noop(scope, provider_name, *, ok):
        return None

    async def _budget_ok(scope, daily_budget):
        return True

    monkeypatch.setattr(provider, "circuit_is_open", _not_open)
    monkeypatch.setattr(provider, "record_provider_result", _record_noop)
    monkeypatch.setattr(provider, "check_tool_budget", _budget_ok)


async def test_run_chain_retries_same_provider_once_after_429_then_succeeds(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)

    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    responses = [_response(429), _response(200, "hello")]

    async def fake_post(self, url, headers=None, json=None):
        return responses.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    content, used_provider = await provider._run_chain("prompt", "system", 100, "heavy")

    assert content == "hello"
    assert used_provider == "groq"
    assert sleep_calls == [provider._RATE_LIMIT_BACKOFF_SECONDS]
    assert responses == []


async def test_run_chain_falls_through_to_next_provider_if_retry_also_rate_limited(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    # groq: 429, retry: 429 again -> falls through to openrouter: 200
    responses = [_response(429), _response(429), _response(200, "from openrouter")]

    async def fake_post(self, url, headers=None, json=None):
        return responses.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    content, used_provider = await provider._run_chain("prompt", "system", 100, "heavy")

    assert content == "from openrouter"
    assert used_provider == "openrouter"
    assert responses == []


# ── stream_text / _openai_compat_stream ─────────────────────────────────
# Covers two things added this session that had zero coverage on the
# streaming path specifically (the non-streaming path already had the
# reasoning_effort fix; this path never had it at all until a real cover
# letter streamed fine up to "...initiatives in a" and silently stopped —
# see generation hit-live notes in cover_letter/routes.py):
#   1. reasoning_effort is included in the request body only for a
#      gpt-oss-class model (sending it to any other model is a 400 per
#      Groq's API).
#   2. finish_reason == "length" is detected and logged as a warning (not
#      raised — content has already been yielded by that point, same
#      "don't switch mid-stream" reasoning as everywhere else in this file).

class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b"error body"


class _FakeStreamCM:
    def __init__(self, resp: _FakeStreamResponse):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


def _sse_lines(*deltas_and_finish: tuple[str | None, str | None]) -> list[str]:
    """Builds fake 'data: {...}' SSE lines from (content_delta, finish_reason)
    pairs, terminated with the real API's 'data: [DONE]' sentinel."""
    lines = []
    for content, finish_reason in deltas_and_finish:
        delta = {"content": content} if content is not None else {}
        payload = {"choices": [{"delta": delta, "finish_reason": finish_reason}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append("data: [DONE]")
    return lines


async def test_stream_text_includes_reasoning_effort_for_gpt_oss_model(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")

    captured: dict = {}

    def fake_stream(self, method, url, headers=None, json=None):
        captured["body"] = json
        return _FakeStreamCM(_FakeStreamResponse(200, _sse_lines(("Hello", None), (None, "stop"))))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    chunks = [c async for c in provider.stream_text("prompt", "system", reasoning_effort="low")]

    assert "".join(chunks) == "Hello"
    assert captured["body"]["reasoning_effort"] == "low"


async def test_stream_text_omits_reasoning_effort_for_non_gpt_oss_model(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)
    monkeypatch.setattr(settings, "groq_model", "llama-3.3-70b-versatile")

    captured: dict = {}

    def fake_stream(self, method, url, headers=None, json=None):
        captured["body"] = json
        return _FakeStreamCM(_FakeStreamResponse(200, _sse_lines(("Hello", None), (None, "stop"))))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    chunks = [c async for c in provider.stream_text("prompt", "system", reasoning_effort="low")]

    assert "".join(chunks) == "Hello"
    assert "reasoning_effort" not in captured["body"]


async def test_stream_text_omits_reasoning_effort_when_not_passed(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)
    monkeypatch.setattr(settings, "groq_model", "openai/gpt-oss-120b")

    captured: dict = {}

    def fake_stream(self, method, url, headers=None, json=None):
        captured["body"] = json
        return _FakeStreamCM(_FakeStreamResponse(200, _sse_lines(("Hi", "stop"))))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    _ = [c async for c in provider.stream_text("prompt", "system")]

    assert "reasoning_effort" not in captured["body"]


async def test_stream_text_logs_warning_on_length_truncation(monkeypatch, caplog):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)

    def fake_stream(self, method, url, headers=None, json=None):
        return _FakeStreamCM(_FakeStreamResponse(200, _sse_lines(("Cut off mid", "length"))))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    with caplog.at_level("WARNING"):
        chunks = [c async for c in provider.stream_text("prompt", "system")]

    assert "".join(chunks) == "Cut off mid"
    assert any("length" in rec.message and "truncat" in rec.message for rec in caplog.records)


async def test_stream_text_no_warning_on_normal_completion(monkeypatch, caplog):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)

    def fake_stream(self, method, url, headers=None, json=None):
        return _FakeStreamCM(_FakeStreamResponse(200, _sse_lines(("All done", "stop"))))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    with caplog.at_level("WARNING"):
        chunks = [c async for c in provider.stream_text("prompt", "system")]

    assert "".join(chunks) == "All done"
    assert not any("truncat" in rec.message for rec in caplog.records)


async def test_run_chain_raises_after_all_providers_exhausted_on_429(monkeypatch):
    _patch_settings(monkeypatch)
    _patch_cache_bypass(monkeypatch)

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(provider.asyncio, "sleep", fake_sleep)

    # groq initial 429, groq retry 429 -> openrouter initial 429, openrouter retry 429 -> exhausted
    responses = [_response(429), _response(429), _response(429), _response(429)]

    async def fake_post(self, url, headers=None, json=None):
        return responses.pop(0)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    try:
        await provider._run_chain("prompt", "system", 100, "heavy")
        assert False, "expected AIGenerationError"
    except provider.AIGenerationError:
        pass

    assert responses == []
