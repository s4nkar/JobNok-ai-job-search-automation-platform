"""Unit tests for startup_scout.schemas — custom field validators only
(funding_stage allowlist, website scheme check). Framework-provided
constraints like Field(min_length=...)/Field(ge=...) are exercised only
where they interact with the custom validator, not re-tested in isolation.
"""

import pytest
from pydantic import ValidationError

from app.modules.startup_scout.schemas import ScoutSearchRequest, SaveCompanyRequest


def test_scout_search_request_accepts_known_funding_stage():
    req = ScoutSearchRequest(location="Berlin", funding_stage="series-b")
    assert req.funding_stage == "series-b"


def test_scout_search_request_rejects_unknown_funding_stage():
    with pytest.raises(ValidationError) as exc_info:
        ScoutSearchRequest(location="Berlin", funding_stage="unicorn")
    assert "Unknown funding stage" in str(exc_info.value)


def test_scout_search_request_defaults_funding_stage_to_seed():
    req = ScoutSearchRequest(location="Berlin")
    assert req.funding_stage == "seed"


def test_scout_search_request_limit_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        ScoutSearchRequest(location="Berlin", limit=5)  # below ge=10
    with pytest.raises(ValidationError):
        ScoutSearchRequest(location="Berlin", limit=500)  # above le=200


def test_scout_search_request_blank_location_rejected():
    with pytest.raises(ValidationError):
        ScoutSearchRequest(location="")


def test_save_company_request_accepts_http_and_https_website():
    assert SaveCompanyRequest(name="Acme", website="http://acme.com").website == "http://acme.com"
    assert SaveCompanyRequest(name="Acme", website="https://acme.com").website == "https://acme.com"


def test_save_company_request_accepts_empty_website():
    assert SaveCompanyRequest(name="Acme", website="").website == ""


def test_save_company_request_rejects_website_without_scheme():
    with pytest.raises(ValidationError) as exc_info:
        SaveCompanyRequest(name="Acme", website="acme.com")
    assert "http or https" in str(exc_info.value)
