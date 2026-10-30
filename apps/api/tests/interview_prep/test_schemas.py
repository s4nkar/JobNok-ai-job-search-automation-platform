"""Unit tests for interview_prep.schemas — pure Pydantic validation and the
field-by-field lenient validators, no I/O, no mocking needed."""

import pytest
from pydantic import ValidationError

from app.modules.interview_prep.schemas import (
    InterviewPrepRequest,
    InterviewRegenerateRequest,
    validate_interview_response,
    validate_regenerate_response,
)


def test_interview_prep_request_accepts_valid_input():
    req = InterviewPrepRequest(job_description="A" * 50)
    assert req.company is None
    assert req.role is None
    assert req.opportunity_id is None
    assert req.job_search_application_id is None
    assert req.session_id is None


def test_interview_prep_request_accepts_linkage_and_session_ids():
    req = InterviewPrepRequest(job_description="A" * 50, opportunity_id="opp-1", session_id="sess-1")
    assert req.opportunity_id == "opp-1"
    assert req.session_id == "sess-1"


def test_interview_prep_request_accepts_optional_company_and_role():
    req = InterviewPrepRequest(job_description="A" * 50, company="Acme Corp", role="AI Engineer")
    assert req.company == "Acme Corp"
    assert req.role == "AI Engineer"


def test_interview_prep_request_rejects_too_short_job_description():
    with pytest.raises(ValidationError):
        InterviewPrepRequest(job_description="too short")


def test_interview_prep_request_enforces_max_length():
    with pytest.raises(ValidationError):
        InterviewPrepRequest(job_description="A" * 12001)
    InterviewPrepRequest(job_description="A" * 12000)


def test_interview_regenerate_request_accepts_valid_input():
    req = InterviewRegenerateRequest(job_description="A" * 50, question="Tell me about a time...")
    assert req.question.startswith("Tell me")


def test_interview_regenerate_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        InterviewRegenerateRequest(job_description="A" * 50, question="")


def test_interview_regenerate_request_enforces_question_max_length():
    with pytest.raises(ValidationError):
        InterviewRegenerateRequest(job_description="A" * 50, question="x" * 501)
    InterviewRegenerateRequest(job_description="A" * 50, question="x" * 500)


def _valid_response_payload():
    return {
        "role_assessment": {
            "seniority": "mid",
            "role_family": "AI/ML Engineer",
            "likely_rounds": ["Recruiter screen", "Technical screen"],
            "company_context": None,
            "dsa_likely": True,
            "system_design_likely": False,
        },
        "questions": [
            {
                "question": "Tell me about a challenging project.",
                "framework": "STAR",
                "answer_framework": "Describe the situation, task, action, result.",
                "tips": ["Be specific", "Quantify impact"],
            },
        ],
        "dsa_questions": [
            {"question": "Reverse a linked list", "approach": "Use three pointers, O(n) time."},
        ],
        "system_design_questions": [],
    }


def test_validate_interview_response_passes_through_valid_payload():
    result = validate_interview_response(_valid_response_payload())
    assert result["role_assessment"]["seniority"] == "mid"
    assert result["role_assessment"]["dsa_likely"] is True
    assert len(result["questions"]) == 1
    assert result["questions"][0]["framework"] == "STAR"
    assert len(result["dsa_questions"]) == 1
    assert result["system_design_questions"] == []


def test_validate_interview_response_falls_back_on_invalid_seniority():
    payload = _valid_response_payload()
    payload["role_assessment"]["seniority"] = "not-a-real-value"
    result = validate_interview_response(payload)
    # The whole role_assessment field falls back to its default (unclear,
    # dsa/system_design both false) - one bad nested key invalidates just
    # this top-level field, not the rest of the response.
    assert result["role_assessment"]["seniority"] == "unclear"
    assert result["role_assessment"]["dsa_likely"] is False
    # Sibling top-level fields are untouched by the other field's failure.
    assert len(result["questions"]) == 1


def test_validate_interview_response_falls_back_on_malformed_questions():
    payload = _valid_response_payload()
    payload["questions"] = "not a list"
    result = validate_interview_response(payload)
    assert result["questions"] == []
    assert result["role_assessment"]["seniority"] == "mid"


def test_validate_interview_response_defaults_missing_top_level_fields():
    result = validate_interview_response({})
    assert result["role_assessment"]["seniority"] == "unclear"
    assert result["questions"] == []
    assert result["dsa_questions"] == []
    assert result["system_design_questions"] == []


def test_validate_regenerate_response_passes_through_valid_payload():
    result = validate_regenerate_response({"answer_framework": "Use STAR.", "tips": ["Be concise", "Give a result"]})
    assert result["answer_framework"] == "Use STAR."
    assert result["tips"] == ["Be concise", "Give a result"]


def test_validate_regenerate_response_falls_back_on_malformed_tips():
    result = validate_regenerate_response({"answer_framework": "Use STAR.", "tips": "not a list"})
    assert result["answer_framework"] == "Use STAR."
    assert result["tips"] == []


def test_interview_regenerate_request_accepts_session_id_and_question_index():
    req = InterviewRegenerateRequest(
        job_description="A" * 50, question="Tell me about a time...", session_id="sess-1", question_index=2,
    )
    assert req.session_id == "sess-1"
    assert req.question_index == 2


def test_interview_regenerate_request_rejects_negative_question_index():
    with pytest.raises(ValidationError):
        InterviewRegenerateRequest(job_description="A" * 50, question="x", question_index=-1)
