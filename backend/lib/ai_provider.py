"""AI provider abstraction — supports Anthropic Claude and HuggingFace free inference.

Switch providers via:
    AI_PROVIDER=anthropic   AI_MODEL=claude-sonnet-4-6
    AI_PROVIDER=huggingface AI_MODEL=mistralai/Mistral-7B-Instruct-v0.3

Both providers expose the same interface:
    generate_text(prompt, system, max_tokens) -> str
    stream_text(prompt, system, max_tokens)   -> AsyncGenerator[str]
"""

from __future__ import annotations

import json
from typing import AsyncGenerator

from lib.config import settings


# ── Anthropic ────────────────────────────────────────────────────

async def _anthropic_generate(prompt: str, system: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _anthropic_stream(prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    with client.messages.stream(
        model=settings.ai_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── HuggingFace ──────────────────────────────────────────────────

def _format_hf_prompt(prompt: str, system: str) -> str:
    """Format prompt for instruction-tuned models (Mistral/Llama style)."""
    if system:
        return f"<s>[INST] {system}\n\n{prompt} [/INST]"
    return f"<s>[INST] {prompt} [/INST]"


async def _huggingface_generate(prompt: str, system: str, max_tokens: int) -> str:
    from huggingface_hub import InferenceClient
    token = settings.huggingface_api_key or None
    client = InferenceClient(model=settings.huggingface_model, token=token)
    formatted = _format_hf_prompt(prompt, system)
    output = client.text_generation(
        formatted,
        max_new_tokens=max_tokens,
        do_sample=True,
        temperature=0.7,
    )
    return output


async def _huggingface_stream(prompt: str, system: str, max_tokens: int) -> AsyncGenerator[str, None]:
    from huggingface_hub import InferenceClient
    token = settings.huggingface_api_key or None
    client = InferenceClient(model=settings.huggingface_model, token=token)
    formatted = _format_hf_prompt(prompt, system)
    for token_text in client.text_generation(
        formatted,
        max_new_tokens=max_tokens,
        do_sample=True,
        temperature=0.7,
        stream=True,
    ):
        yield token_text


# ── Public Interface ─────────────────────────────────────────────

async def generate_text(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> str:
    provider = settings.ai_provider.lower()
    if provider == "anthropic":
        return await _anthropic_generate(prompt, system, max_tokens)
    elif provider == "huggingface":
        return await _huggingface_generate(prompt, system, min(max_tokens, settings.huggingface_max_tokens))
    raise ValueError(f"Unknown AI provider: {settings.ai_provider!r}. Set AI_PROVIDER=anthropic or AI_PROVIDER=huggingface in .env")


async def stream_text(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    provider = settings.ai_provider.lower()
    if provider == "anthropic":
        async for chunk in _anthropic_stream(prompt, system, max_tokens):
            yield chunk
    elif provider == "huggingface":
        async for chunk in _huggingface_stream(prompt, system, min(max_tokens, settings.huggingface_max_tokens)):
            yield chunk
    else:
        raise ValueError(f"Unknown AI provider: {settings.ai_provider!r}. Set AI_PROVIDER=anthropic or AI_PROVIDER=huggingface in .env")
