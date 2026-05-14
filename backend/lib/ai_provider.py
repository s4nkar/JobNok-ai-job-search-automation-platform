"""AI provider abstraction — Groq, Cerebras, Anthropic, HuggingFace.

Configured via env:
    AI_PROVIDER=groq           # primary
    AI_FALLBACK_CHAIN=cerebras,huggingface   # tried in order on transient failures

Groq and Cerebras both expose OpenAI-compatible REST APIs and are reached via
httpx — no extra SDK. Anthropic and HuggingFace keep their existing clients.

Public interface (unchanged):
    generate_text(prompt, system, max_tokens) -> str
    stream_text(prompt, system, max_tokens)   -> AsyncGenerator[str, None]

Failure semantics:
    - generate_text retries the next provider on rate-limit / 5xx / network errors.
    - stream_text retries the next provider ONLY if the first provider fails before
      yielding any tokens. Once a stream has started emitting, we do not switch
      mid-stream (would produce garbled output).
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import httpx

from lib.config import settings

logger = logging.getLogger(__name__)


class _ProviderError(Exception):
    """Transient provider failure — caller should try the next provider."""


class _ProviderUnavailable(_ProviderError):
    """Provider is not configured (e.g. missing API key) — skip without logging as error."""


# ── OpenAI-compatible (Groq, Cerebras) ────────────────────────────

async def _openai_compat_generate(
    prompt: str, system: str, max_tokens: int,
    base_url: str, api_key: str, model: str, label: str,
) -> str:
    if not api_key:
        raise _ProviderUnavailable(f"{label}: API key not configured")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        async with httpx.AsyncClient(timeout=settings.ai_request_timeout_seconds) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
            )
    except httpx.HTTPError as exc:
        raise _ProviderError(f"{label} network error: {exc!r}") from exc

    if resp.status_code == 429 or resp.status_code >= 500:
        raise _ProviderError(f"{label} HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        # 4xx (other than 429) usually means bad request — don't retry on another provider
        # because the request itself is the problem.
        raise RuntimeError(f"{label} HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise _ProviderError(f"{label} malformed response: {exc!r}") from exc


async def _openai_compat_stream(
    prompt: str, system: str, max_tokens: int,
    base_url: str, api_key: str, model: str, label: str,
) -> AsyncGenerator[str, None]:
    if not api_key:
        raise _ProviderUnavailable(f"{label}: API key not configured")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # No client-level timeout on streams — long-running by nature. We rely on the
    # server to terminate; connect timeout still applies.
    timeout = httpx.Timeout(connect=15.0, read=None, write=15.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model, "messages": messages,
                    "max_tokens": max_tokens, "temperature": 0.7, "stream": True,
                },
            ) as resp:
                if resp.status_code == 429 or resp.status_code >= 500:
                    body = await resp.aread()
                    raise _ProviderError(f"{label} HTTP {resp.status_code}: {body[:200]!r}")
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(f"{label} HTTP {resp.status_code}: {body[:200]!r}")

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        # Skip malformed SSE frames silently — stream continues.
                        continue
        except httpx.HTTPError as exc:
            raise _ProviderError(f"{label} network error: {exc!r}") from exc


# ── Anthropic ────────────────────────────────────────────────────

async def _anthropic_generate(prompt: str, system: str, max_tokens: int) -> str:
    if not settings.anthropic_api_key:
        raise _ProviderUnavailable("anthropic: API key not configured")
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        message = await client.messages.create(
            model=settings.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except anthropic.APIStatusError as exc:
        if exc.status_code == 429 or exc.status_code >= 500:
            raise _ProviderError(f"anthropic HTTP {exc.status_code}") from exc
        raise


async def _anthropic_stream(prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
    if not settings.anthropic_api_key:
        raise _ProviderUnavailable("anthropic: API key not configured")
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        async with client.messages.stream(
            model=settings.ai_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except anthropic.APIStatusError as exc:
        if exc.status_code == 429 or exc.status_code >= 500:
            raise _ProviderError(f"anthropic HTTP {exc.status_code}") from exc
        raise


# ── HuggingFace ──────────────────────────────────────────────────

def _hf_raise(exc: Exception) -> None:
    """Re-raise HuggingFace errors with the right semantics.

    429 / 5xx → _ProviderError (transient, try next provider).
    400        → RuntimeError  (bad request / model config — retrying won't help).
    """
    from huggingface_hub.utils import HfHubHTTPError
    if isinstance(exc, HfHubHTTPError) and exc.response is not None:
        if exc.response.status_code == 429 or exc.response.status_code >= 500:
            raise _ProviderError(f"huggingface error: {exc!r}") from exc
        # 400 "model not supported" — hard failure; don't burn the fallback chain.
        raise RuntimeError(f"huggingface error: {exc!r}") from exc
    raise _ProviderError(f"huggingface error: {exc!r}") from exc


async def _huggingface_generate(prompt: str, system: str, max_tokens: int) -> str:
    from huggingface_hub import InferenceClient
    from huggingface_hub.utils import HfHubHTTPError

    client = InferenceClient(provider="auto", api_key=settings.huggingface_api_key or None)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=settings.huggingface_model,
            messages=messages,
            max_tokens=min(max_tokens, settings.huggingface_max_tokens),
            temperature=0.7,
        )
        return response.choices[0].message.content or ""
    except HfHubHTTPError as exc:
        _hf_raise(exc)
        raise  # unreachable — keeps type checker happy


async def _huggingface_stream(prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
    from huggingface_hub import InferenceClient
    from huggingface_hub.utils import HfHubHTTPError

    client = InferenceClient(provider="auto", api_key=settings.huggingface_api_key or None)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        stream = client.chat.completions.create(
            model=settings.huggingface_model,
            messages=messages,
            max_tokens=min(max_tokens, settings.huggingface_max_tokens),
            temperature=0.7,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except HfHubHTTPError as exc:
        _hf_raise(exc)
        raise  # unreachable


# ── Provider dispatch ────────────────────────────────────────────

def _provider_chain() -> list[str]:
    primary = settings.ai_provider.lower().strip()
    fallbacks = [p.strip().lower() for p in settings.ai_fallback_chain.split(",") if p.strip()]
    chain = [primary] + [p for p in fallbacks if p != primary]
    return chain


async def _dispatch_generate(provider: str, prompt: str, system: str, max_tokens: int) -> str:
    if provider == "groq":
        return await _openai_compat_generate(
            prompt, system, max_tokens,
            settings.groq_base_url, settings.groq_api_key, settings.groq_model, "groq",
        )
    if provider == "cerebras":
        return await _openai_compat_generate(
            prompt, system, max_tokens,
            settings.cerebras_base_url, settings.cerebras_api_key, settings.cerebras_model, "cerebras",
        )
    if provider == "anthropic":
        return await _anthropic_generate(prompt, system, max_tokens)
    if provider == "huggingface":
        return await _huggingface_generate(prompt, system, max_tokens)
    raise ValueError(f"Unknown AI provider: {provider!r}")


def _dispatch_stream(provider: str, prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
    if provider == "groq":
        return _openai_compat_stream(
            prompt, system, max_tokens,
            settings.groq_base_url, settings.groq_api_key, settings.groq_model, "groq",
        )
    if provider == "cerebras":
        return _openai_compat_stream(
            prompt, system, max_tokens,
            settings.cerebras_base_url, settings.cerebras_api_key, settings.cerebras_model, "cerebras",
        )
    if provider == "anthropic":
        return _anthropic_stream(prompt, system, max_tokens)
    if provider == "huggingface":
        return _huggingface_stream(prompt, system, max_tokens)
    raise ValueError(f"Unknown AI provider: {provider!r}")


# ── Public Interface ─────────────────────────────────────────────

async def generate_text(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    chain = _provider_chain()
    last_error: Exception | None = None
    for provider in chain:
        try:
            return await _dispatch_generate(provider, prompt, system, max_tokens)
        except _ProviderUnavailable as exc:
            logger.info("ai_provider skip %s: %s", provider, exc)
            last_error = exc
            continue
        except _ProviderError as exc:
            logger.warning("ai_provider transient failure on %s: %s", provider, exc)
            last_error = exc
            continue
    raise RuntimeError(f"All AI providers exhausted ({chain}). Last error: {last_error!r}")


async def stream_text(prompt: str, system: str = "", max_tokens: int = 2048) -> AsyncGenerator[str, None]:
    chain = _provider_chain()
    last_error: Exception | None = None

    for provider in chain:
        try:
            gen = _dispatch_stream(provider, prompt, system, max_tokens)
            # Pull the first chunk eagerly so we can fall back on a clean failure
            # before any bytes reach the client.
            first_iter = gen.__aiter__()
            try:
                first_chunk = await first_iter.__anext__()
            except StopAsyncIteration:
                # Provider returned an empty stream — treat as a transient failure.
                last_error = _ProviderError(f"{provider} returned empty stream")
                logger.warning("ai_provider empty stream on %s", provider)
                continue
            yield first_chunk
            async for chunk in first_iter:
                yield chunk
            return
        except _ProviderUnavailable as exc:
            logger.info("ai_provider skip %s: %s", provider, exc)
            last_error = exc
            continue
        except _ProviderError as exc:
            logger.warning("ai_provider transient failure on %s: %s", provider, exc)
            last_error = exc
            continue

    yield f"\n\nAI provider error: all providers exhausted. Last error: {last_error!r}"
