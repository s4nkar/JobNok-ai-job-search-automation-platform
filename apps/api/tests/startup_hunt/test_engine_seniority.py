"""Unit tests for engine.py's seniority-preference inference and years-of-
experience filtering - pure functions that gate which roles survive
_score_opportunity's seniority checks (see test_engine_scoring.py)."""

from app.modules.startup_hunt import engine


def test_normalize_seniority_preference_exact_junior_terms():
    assert engine._normalize_seniority_preference("entry level") == "junior"
    assert engine._normalize_seniority_preference("intern") == "junior"


def test_normalize_seniority_preference_exact_mid_terms():
    assert engine._normalize_seniority_preference("mid-level") == "mid"
    assert engine._normalize_seniority_preference("individual contributor") == "mid"


def test_normalize_seniority_preference_exact_senior_terms():
    assert engine._normalize_seniority_preference("senior") == "senior"
    assert engine._normalize_seniority_preference("lead") == "senior"


def test_normalize_seniority_preference_exact_staff_terms():
    assert engine._normalize_seniority_preference("principal") == "staff_plus"
    assert engine._normalize_seniority_preference("director") == "staff_plus"


def test_normalize_seniority_preference_fuzzy_substring_fallback():
    assert engine._normalize_seniority_preference("junior-ish role") == "junior"
    assert engine._normalize_seniority_preference("staff engineer track") == "staff_plus"


def test_normalize_seniority_preference_none_for_unrecognized_or_empty():
    assert engine._normalize_seniority_preference("potato") is None
    assert engine._normalize_seniority_preference(None) is None
    assert engine._normalize_seniority_preference("") is None


def test_infer_seniority_preference_from_prompt_junior_signals():
    assert engine._infer_seniority_preference_from_prompt("Looking for an entry-level AI role") == "junior"


def test_infer_seniority_preference_from_prompt_mid_signals():
    assert engine._infer_seniority_preference_from_prompt("I have 3+ years experience, not senior") == "mid"


def test_infer_seniority_preference_from_prompt_senior_signals():
    assert engine._infer_seniority_preference_from_prompt("Only senior or staff roles") == "senior"


def test_infer_seniority_preference_from_prompt_none_when_blank_or_unmatched():
    assert engine._infer_seniority_preference_from_prompt(None) is None
    assert engine._infer_seniority_preference_from_prompt("Remote AI roles in Berlin") is None


def test_strict_mid_level_preference_true_only_when_mid_and_explicit_language():
    assert engine._strict_mid_level_preference("3+ years, not senior please", "mid") is True


def test_strict_mid_level_preference_false_when_preference_not_mid():
    assert engine._strict_mid_level_preference("3+ years, not senior please", "senior") is False


def test_strict_mid_level_preference_false_without_explicit_mid_language():
    assert engine._strict_mid_level_preference("I like AI roles", "mid") is False


def test_extract_min_years_required_plus_pattern():
    assert engine._extract_min_years_required("Requires 5+ years of experience") == 5


def test_extract_min_years_required_range_pattern_uses_lower_bound():
    assert engine._extract_min_years_required("3-5 years experience required") == 3


def test_extract_min_years_required_minimum_phrase():
    assert engine._extract_min_years_required("at least 4 years experience") == 4


def test_extract_min_years_required_none_when_no_match():
    assert engine._extract_min_years_required("Great team, flexible hours") is None


def test_extract_min_years_required_ignores_absurd_values():
    assert engine._extract_min_years_required("99 years experience") is None


def test_extract_min_years_required_takes_minimum_of_multiple_mentions():
    text = "2 years experience minimum, though 6 years experience is preferred"
    assert engine._extract_min_years_required(text) == 2


def test_max_years_allowed_junior_is_capped_at_two():
    assert engine._max_years_allowed(None, "junior") == 2


def test_max_years_allowed_mid_default_is_five():
    assert engine._max_years_allowed("open to mid level", "mid") == 5


def test_max_years_allowed_mid_honors_explicit_years_in_prompt():
    assert engine._max_years_allowed("3+ years experience", "mid") == 4
    assert engine._max_years_allowed("5+ years", "mid") == 6


def test_max_years_allowed_senior_or_none_preference_is_unbounded():
    assert engine._max_years_allowed("anything", "senior") is None
    assert engine._max_years_allowed("anything", None) is None


def test_role_seniority_level_detects_staff_plus():
    assert engine._role_seniority_level("Head of AI", "") == "staff_plus"
    assert engine._role_seniority_level("Principal Engineer", "") == "staff_plus"


def test_role_seniority_level_detects_senior():
    assert engine._role_seniority_level("Senior ML Engineer", "") == "senior"


def test_role_seniority_level_detects_junior():
    assert engine._role_seniority_level("Junior AI Engineer", "") == "junior"
    assert engine._role_seniority_level("Werkstudent AI", "") == "junior"


def test_role_seniority_level_defaults_to_mid():
    assert engine._role_seniority_level("AI Engineer", "") == "mid"


def test_role_seniority_level_checks_raw_text_too():
    assert engine._role_seniority_level("AI Engineer", "this is a principal-level role") == "staff_plus"
