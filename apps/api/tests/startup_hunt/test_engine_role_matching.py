"""Unit tests for engine.py's query<->role-title/body matching heuristics -
the deterministic filters _score_opportunity relies on to decide whether a
result is even in the right role family before scoring it at all."""

from app.modules.startup_hunt import engine


def test_query_specialty_terms_detects_ai_and_ml():
    terms = engine._query_specialty_terms("Applied AI Engineer")
    assert "ai" in terms


def test_query_specialty_terms_detects_nlp_and_llm():
    terms = engine._query_specialty_terms("LLM / NLP Engineer")
    assert "llm" in terms
    assert "nlp" in terms


def test_query_specialty_terms_empty_for_unrelated_query():
    assert engine._query_specialty_terms("Barista") == []


def test_query_stack_signals_detects_known_signals():
    signals = engine._query_stack_signals("RAG + Agent MLOps FastAPI engineer")
    assert set(signals) == {"rag", "agent", "mlops", "fastapi"}


def test_query_stack_signals_empty_when_none_present():
    assert engine._query_stack_signals("Software Engineer") == []


def test_matches_ai_specialty_query_true_when_no_specialty_in_query():
    assert engine._matches_ai_specialty_query("Software Engineer", "Backend Engineer", "") is True


def test_matches_ai_specialty_query_true_for_known_engineer_alias_in_title():
    assert engine._matches_ai_specialty_query("AI Engineer", "Applied AI Engineer", "") is True


def test_matches_ai_specialty_query_true_when_title_mentions_specialty():
    assert engine._matches_ai_specialty_query("LLM Engineer", "LLM Platform Lead", "") is True


def test_matches_ai_specialty_query_false_when_specialty_absent_everywhere():
    assert engine._matches_ai_specialty_query("NLP Engineer", "Backend Engineer", "general web backend role") is False


def test_role_title_matches_query_true_for_ai_family_title():
    assert engine._role_title_matches_query("AI Engineer", "Applied AI Engineer", "") is True


def test_role_title_matches_query_false_when_ai_query_but_no_ai_signal_anywhere():
    assert engine._role_title_matches_query("AI Engineer", "Backend Engineer", "general web backend role") is False


def test_role_title_matches_query_true_when_ai_signal_in_body_with_function_token():
    assert engine._role_title_matches_query("AI Engineer", "Platform Engineer", "builds our machine learning pipeline") is True


def test_role_title_matches_query_non_ai_query_requires_function_group():
    assert engine._role_title_matches_query("Data Scientist", "Data Engineer", "") is False
    assert engine._role_title_matches_query("Data Scientist", "Data Scientist", "") is True


def test_role_title_matches_query_non_ai_manager_query_accepts_lead_title():
    assert engine._role_title_matches_query("Engineering Manager", "Engineering Lead", "") is True
