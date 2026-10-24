"""Unit tests for engine.py's _score_opportunity - the deterministic
filter+scoring pipeline each raw search result goes through before display.
Pure function of (item, payload, strategy, existing_opportunities), no I/O."""

from app.modules.startup_hunt import engine


def _payload(**overrides) -> dict:
    base = {
        "query": "AI Engineer",
        "location": "Berlin",
        "country": "Germany",
        "strategy_prompt": None,
        "direct_links_only": False,
        "english_friendly_only": False,
        "company_stage": None,
        "remote_only": False,
        "posted_within_hours": None,
    }
    base.update(overrides)
    return base


def _strategy(**overrides) -> dict:
    base = {
        "keywords": [],
        "languages": [],
        "company_stage": None,
        "preferred_cities": [],
        "hidden_gem_signals": [],
        "contact_focus": [],
        "seniority_preference": None,
    }
    base.update(overrides)
    return base


def _item(**overrides) -> dict:
    base = {
        "role_title": "AI Engineer",
        "location": "Berlin, Germany",
        "country": "Germany",
        "raw_text": "AI Engineer role building machine learning pipelines",
        "company_payload": {},
        "direct_apply_url": None,
        "contacts": [],
        "posted_at": None,
        "opportunity_kind": "job",
        "company_name": "Acme AI",
        "company_domain": "acme.ai",
        "company_website_url": "https://acme.ai",
        "company_careers_url": None,
        "source_name": "Greenhouse",
        "source_type": "greenhouse",
        "canonical_job_url": "https://acme.ai/jobs/1",
        "portal_job_url": None,
        "citation": {"evidence": []},
    }
    base.update(overrides)
    return base


def test_score_opportunity_filters_out_missing_keyword_match():
    item = _item(
        role_title="Product Manager",
        raw_text="leads roadmap and go-to-market strategy for enterprise clients",
    )
    scored, reason = engine._score_opportunity(item, _payload(), _strategy(), {})
    assert scored is None
    assert reason == "Missing query keyword match"


def test_score_opportunity_filters_out_wrong_role_family():
    item = _item(role_title="Sales Representative", raw_text="AI startup looking for sales rep, engineer team separate")
    scored, reason = engine._score_opportunity(item, _payload(), _strategy(), {})
    assert scored is None
    assert reason == "Role title did not match requested role family"


def test_score_opportunity_filters_out_location_mismatch():
    item = _item(location="Paris, France", country="France")
    scored, reason = engine._score_opportunity(item, _payload(location="Berlin", country="Germany"), _strategy(), {})
    assert scored is None
    assert reason == "Location filter removed this result"


def test_score_opportunity_filters_out_direct_links_only():
    item = _item(direct_apply_url=None)
    scored, reason = engine._score_opportunity(item, _payload(direct_links_only=True), _strategy(), {})
    assert scored is None
    assert reason == "Direct links only filter removed this result"


def test_score_opportunity_filters_out_remote_only_when_not_remote():
    item = _item(location="Berlin, Germany")
    scored, reason = engine._score_opportunity(item, _payload(remote_only=True), _strategy(), {})
    assert scored is None
    assert reason == "Remote-only filter removed this result"


def test_score_opportunity_filters_out_company_stage_mismatch():
    item = _item(company_payload={"stage": "Series C"})
    scored, reason = engine._score_opportunity(item, _payload(company_stage="seed"), _strategy(), {})
    assert scored is None
    assert reason == "Company stage filter removed this result"


def test_score_opportunity_filters_out_senior_role_when_strict_mid_requested():
    item = _item(role_title="Senior AI Engineer")
    payload = _payload(strategy_prompt="3+ years experience, not senior")
    scored, reason = engine._score_opportunity(item, payload, _strategy(), {})
    assert scored is None
    assert reason == "Role seniority exceeded the requested mid-level range"


def test_score_opportunity_filters_out_excess_years_requirement():
    item = _item(raw_text="AI Engineer role requiring 8+ years of experience")
    payload = _payload(strategy_prompt="entry level, 0-2 years")
    scored, reason = engine._score_opportunity(item, payload, _strategy(), {})
    assert scored is None
    assert "years experience" in reason


def test_score_opportunity_accepts_matching_role_and_returns_positive_score():
    item = _item()
    scored, reason = engine._score_opportunity(item, _payload(), _strategy(), {})
    assert reason is None
    assert scored is not None
    assert scored["score_total"] > 0
    assert scored["company_name"] == "Acme AI"
    assert scored["source_bucket"] == "ats"


def test_score_opportunity_awards_direct_apply_label_and_bonus():
    item = _item(direct_apply_url="https://acme.ai/apply")
    scored, _ = engine._score_opportunity(item, _payload(), _strategy(), {})
    assert "Direct Apply" in scored["score_labels"]


def test_score_opportunity_penalizes_senior_title_for_mid_preference():
    mid_item = _item(role_title="AI Engineer")
    senior_item = _item(role_title="Staff AI Engineer", raw_text="Staff AI Engineer role, individual contributor track")
    strategy = _strategy(seniority_preference="mid")
    mid_scored, _ = engine._score_opportunity(mid_item, _payload(), strategy, {})
    senior_scored, _ = engine._score_opportunity(senior_item, _payload(), strategy, {})
    assert mid_scored["score_total"] > senior_scored["score_total"]


def test_score_opportunity_marks_saved_state_from_existing_opportunities():
    item = _item()
    existing = {"https://acme.ai/jobs/1": {"opportunity_status": "applied", "id": "abc-123"}}
    scored, _ = engine._score_opportunity(item, _payload(), _strategy(), existing)
    assert scored["saved"] is True
    assert scored["saved_status"] == "applied"
    assert scored["saved_opportunity_id"] == "abc-123"


def test_score_opportunity_outreach_lead_bypasses_keyword_and_role_filters_with_ai_relevance():
    item = _item(
        role_title="Founder Outreach",
        raw_text="general startup lead with no explicit role match",
        opportunity_kind="outreach_lead",
        company_payload={"ai_relevance": "building ai copilots for devs"},
    )
    scored, reason = engine._score_opportunity(item, _payload(), _strategy(), {})
    assert reason is None
    assert scored is not None


def test_looks_startup_focused_true_when_company_stage_filter_set():
    assert engine._looks_startup_focused(_payload(company_stage="seed"), _strategy()) is True


def test_looks_startup_focused_true_from_prompt_keywords():
    assert engine._looks_startup_focused(_payload(strategy_prompt="hidden gems only"), _strategy()) is True


def test_looks_startup_focused_false_otherwise():
    assert engine._looks_startup_focused(_payload(), _strategy()) is False


def test_is_startup_sized_true_for_small_team_strings():
    assert engine._is_startup_sized("11 to 50") is True
    assert engine._is_startup_sized("") is False


def test_is_large_company_true_for_enterprise_strings():
    assert engine._is_large_company("10,000+") is True
    assert engine._is_large_company("11 to 50") is False


def test_short_company_signal_truncates_at_word_boundary_and_strips_markdown():
    text = "**Great** # Company " + ("word " * 50)
    result = engine._short_company_signal(text, max_chars=40)
    assert len(result) <= 43  # 40 + "..."
    assert result.endswith("...")
    assert "*" not in result and "#" not in result


def test_short_company_signal_returns_as_is_when_under_limit():
    assert engine._short_company_signal("Short signal", max_chars=160) == "Short signal"
