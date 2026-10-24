"""Unit tests for engine.parse_strategy_prompt - the only AI-call site in
engine.py's non-provider code. ai_provider.generate_text is monkeypatched
directly (no network); cached_prompt_parse is bypassed the same way
test_ai_provider.py bypasses the circuit breaker/budget checks, so this
test never touches real Redis/Upstash."""

from app.modules.startup_hunt import engine


async def _bypass_cache(namespace, prompt, ttl_seconds, parse_fn):
    return await parse_fn()


async def test_parse_strategy_prompt_returns_defaults_for_blank_prompt():
    result = await engine.parse_strategy_prompt(None)
    assert result == {
        "keywords": [],
        "languages": [],
        "company_stage": None,
        "preferred_cities": [],
        "hidden_gem_signals": [],
        "contact_focus": [],
        "seniority_preference": None,
    }


async def test_parse_strategy_prompt_parses_ai_json_response(monkeypatch):
    monkeypatch.setattr(engine, "cached_prompt_parse", _bypass_cache)

    async def fake_generate_text(prompt, system="", max_tokens=2048, tier="heavy", **kwargs):
        return (
            '{"keywords": ["AI", "LLM"], "languages": ["English"], "company_stage": "Seed", '
            '"preferred_cities": ["Berlin"], "hidden_gem_signals": ["Founder-Led"], '
            '"contact_focus": ["Founder"], "seniority_preference": "Senior"}'
        )

    monkeypatch.setattr(engine.ai_provider, "generate_text", fake_generate_text)

    result = await engine.parse_strategy_prompt("Senior AI roles at founder-led startups in Berlin")

    assert result["keywords"] == ["ai", "llm"]
    assert result["languages"] == ["english"]
    assert result["company_stage"] == "seed"
    assert result["preferred_cities"] == ["berlin"]
    assert result["hidden_gem_signals"] == ["founder-led"]
    assert result["contact_focus"] == ["founder"]
    assert result["seniority_preference"] == "senior"


async def test_parse_strategy_prompt_falls_back_to_heuristics_on_ai_failure(monkeypatch):
    monkeypatch.setattr(engine, "cached_prompt_parse", _bypass_cache)

    async def failing_generate_text(prompt, system="", max_tokens=2048, tier="heavy", **kwargs):
        raise RuntimeError("provider exhausted")

    monkeypatch.setattr(engine.ai_provider, "generate_text", failing_generate_text)

    result = await engine.parse_strategy_prompt("Pre-seed startup, English speaking team in Berlin")

    assert result["company_stage"] == "pre-seed"
    assert "english" in result["languages"]
    assert "berlin" in result["preferred_cities"]
    assert set(result["keywords"]) >= {"pre", "seed", "startup", "english", "speaking", "team", "berlin"}


async def test_parse_strategy_prompt_falls_back_when_ai_returns_unparseable_text(monkeypatch):
    monkeypatch.setattr(engine, "cached_prompt_parse", _bypass_cache)

    async def fake_generate_text(prompt, system="", max_tokens=2048, tier="heavy", **kwargs):
        return "not json at all"

    monkeypatch.setattr(engine.ai_provider, "generate_text", fake_generate_text)

    result = await engine.parse_strategy_prompt("hidden gems, founder led")

    assert "hidden gems" in result["hidden_gem_signals"] or "founder-led" in result["hidden_gem_signals"]
