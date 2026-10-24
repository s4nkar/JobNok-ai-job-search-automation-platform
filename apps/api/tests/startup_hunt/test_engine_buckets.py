"""Unit tests for engine.py's source-bucket classification, limits, caps,
and diagnostics - the gating logic that decides which provider buckets run
and how many of each bucket's results survive into the final response."""

from app.modules.startup_hunt import engine
from app.core.config import settings


def _source(**overrides) -> engine.StartupHuntSourceConfig:
    base = dict(type="greenhouse", name="Acme", company="Acme", slug="acme", url=None, metadata={})
    base.update(overrides)
    return engine.StartupHuntSourceConfig(**base)


def test_source_bucket_classifies_ats_providers():
    assert engine._source_bucket(_source(type="greenhouse")) == "ats"
    assert engine._source_bucket(_source(type="lever")) == "ats"
    assert engine._source_bucket(_source(type="ashby")) == "ats"
    assert engine._source_bucket(_source(type="ats_discovery")) == "ats"


def test_source_bucket_classifies_other_providers():
    assert engine._source_bucket(_source(type="indeed_search")) == "indeed"
    assert engine._source_bucket(_source(type="theirstack_search")) == "theirstack"
    assert engine._source_bucket(_source(type="apify_actor")) == "apify"
    assert engine._source_bucket(_source(type="google_web")) == "web"
    assert engine._source_bucket(_source(type="web_search")) == "web"


def test_source_bucket_startup_directory_dynamic_provider_startupmap():
    source = _source(type="startup_directory", metadata={"dynamic_provider": "startupmap"})
    assert engine._source_bucket(source) == "startupmap"


def test_source_bucket_startup_directory_without_dynamic_provider_is_crawler():
    source = _source(type="startup_directory", metadata={})
    assert engine._source_bucket(source) == "crawler"


def test_source_bucket_startup_company_is_crawler():
    assert engine._source_bucket(_source(type="startup_company")) == "crawler"


def test_result_source_bucket_matches_source_bucket_semantics():
    item = {"source_type": "greenhouse", "company_payload": {}}
    assert engine._result_source_bucket(item) == "ats"
    item = {"source_type": "startup_directory", "company_payload": {"dynamic_provider": "startupmap"}}
    assert engine._result_source_bucket(item) == "startupmap"
    item = {"source_type": "unknown_type", "company_payload": {}}
    assert engine._result_source_bucket(item) == "crawler"


def test_bucket_limit_zero_when_bucket_disabled(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", False)
    assert engine._bucket_limit({}, "ats") == 0


def test_bucket_limit_uses_configured_cap_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 7)
    assert engine._bucket_limit({}, "ats") == 7


def test_bucket_limit_unmanaged_bucket_is_always_zero(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_theirstack_enabled", True)
    assert engine._bucket_limit({"theirstack_enabled": True}, "crawler") == 0
    assert engine._bucket_limit({"theirstack_enabled": True}, "apify") == 0


def test_bucket_enabled_theirstack_respects_payload_override(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_theirstack_enabled", True)
    assert engine._bucket_enabled({}, "theirstack") is True
    assert engine._bucket_enabled({"theirstack_enabled": False}, "theirstack") is False


def test_bucket_enabled_theirstack_false_when_config_disabled(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_theirstack_enabled", False)
    assert engine._bucket_enabled({}, "theirstack") is False


def test_bucket_enabled_web_respects_payload_override(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_google_web_enabled", True)
    assert engine._bucket_enabled({}, "web") is True
    assert engine._bucket_enabled({"web_enabled": False}, "web") is False


def test_bucket_enabled_ats_true_if_any_provider_on(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", True)
    assert engine._bucket_enabled({}, "ats") is True


def test_bucket_enabled_unmanaged_bucket_always_false():
    assert engine._bucket_enabled({}, "crawler") is False
    assert engine._bucket_enabled({}, "apify") is False


def test_bucket_available_crawler_requires_include_seeded_sources():
    assert engine._bucket_available({}, "crawler") is False
    assert engine._bucket_available({"include_seeded_sources": True}, "crawler") is True


def test_bucket_available_theirstack_depends_on_api_key(monkeypatch):
    monkeypatch.setattr(settings, "theirstack_api_key", "")
    assert engine._bucket_available({}, "theirstack") is False
    monkeypatch.setattr(settings, "theirstack_api_key", "key-123")
    assert engine._bucket_available({}, "theirstack") is True


def test_effective_result_limit_uses_requested_when_no_bucket_total(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", False)
    sources = [_source(type="greenhouse")]
    assert engine._effective_result_limit({"result_limit": 10}, sources) == 10


def test_effective_result_limit_uses_bucket_total_when_larger(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 15)
    sources = [_source(type="greenhouse")]
    assert engine._effective_result_limit({"result_limit": 5}, sources) == 15


def _scored(bucket: str, score: float = 10.0) -> dict:
    return {"source_bucket": bucket, "score_total": score, "company_name": "Acme", "rank_age_hours": 1.0}


def test_apply_bucket_caps_respects_zero_limit(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", False)
    accepted, counts = engine._apply_bucket_caps([_scored("ats")], {})
    assert accepted == []
    assert counts["ats"] == 0


def test_apply_bucket_caps_enforces_per_bucket_cap(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 1)
    items = [_scored("ats"), _scored("ats")]
    accepted, counts = engine._apply_bucket_caps(items, {})
    assert len(accepted) == 1
    assert counts["ats"] == 1


def test_inactive_bucket_reason_disabled_provider(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", False)
    assert engine._inactive_bucket_reason({}, "ats") == "Provider is disabled for this hunt."


def test_inactive_bucket_reason_crawler_always_reports_disabled():
    # The "crawler" bucket has no entry in _bucket_enabled's flag_map (see
    # engine.py's own comments on it being permanently disabled), so it
    # always short-circuits on the generic "disabled" message before the
    # bucket=="crawler"-specific message below it is ever reached.
    assert engine._inactive_bucket_reason({}, "crawler") == "Provider is disabled for this hunt."


def test_build_source_diagnostics_marks_ok_when_results_accepted(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 15)
    source = _source(type="greenhouse")
    diagnostics = engine._build_source_diagnostics(
        {}, [source], [{"items": [{"x": 1}], "error": None}], {"ats": 1}
    )
    assert diagnostics["ats"]["status"] == "ok"
    assert diagnostics["ats"]["accepted_count"] == 1


def test_build_source_diagnostics_marks_error_when_source_failed(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 15)
    source = _source(type="greenhouse")
    diagnostics = engine._build_source_diagnostics(
        {}, [source], [{"items": [], "error": "boom"}], {"ats": 0}
    )
    assert diagnostics["ats"]["status"] == "error"
    assert diagnostics["ats"]["message"] == "boom"


def test_build_source_diagnostics_inactive_when_not_configured():
    diagnostics = engine._build_source_diagnostics({}, [], [], {})
    assert diagnostics["theirstack"]["configured"] is False
    assert diagnostics["theirstack"]["status"] == "inactive"


def test_limit_source_results_truncates_to_bucket_cap(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", True)
    monkeypatch.setattr(settings, "startup_hunt_ats_result_limit", 2)
    source = _source(type="greenhouse")
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    assert engine._limit_source_results(items, source, {}) == [{"id": 1}, {"id": 2}]


def test_limit_source_results_empty_when_bucket_disabled(monkeypatch):
    monkeypatch.setattr(settings, "startup_hunt_greenhouse_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_lever_enabled", False)
    monkeypatch.setattr(settings, "startup_hunt_ashby_enabled", False)
    source = _source(type="greenhouse")
    assert engine._limit_source_results([{"id": 1}], source, {}) == []
