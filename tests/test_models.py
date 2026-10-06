import pytest
from pydantic import ValidationError
from src.models import (
    ParsedResume,
    ExtractedInfo,
    EligibilityResult,
    GitHubEnrichment,
    GitHubStatus,
    ProjectAssessment,
    ScoreBreakdown,
    RankedCandidate,
    ScreeningReport,
    BatchSummary,
)


def test_models_valid_instantiation():
    assessment = ProjectAssessment(
        ai_project_depth=35,
        python_backend=25,
        cloud_fullstack=10,
        engineering_depth=4,
        thin_wrapper_penalty=2,
        evidence={"ai_project_depth": ["Built RAG system with LangChain"]},
        project_summary="Built agentic RAG system with FastAPI backend.",
        strengths=["Strong RAG experience"],
        concerns=[],
    )
    assert assessment.ai_project_depth == 35

    breakdown = ScoreBreakdown(
        ai_project_depth=35,
        python_backend=25,
        cloud_fullstack=10,
        github=8,
        engineering_depth=4,
    )
    assert breakdown.github == 8

    ranked = RankedCandidate(
        rank=1,
        candidate_name="Alex Doe",
        total_score=75,
        score_breakdown=breakdown,
        thin_wrapper_penalty=2,
        matched_skills=["Python", "FastAPI", "LangChain"],
        source_file="test.pdf",
    )
    assert ranked.total_score == 75


def test_models_bounds_validation():
    with pytest.raises(ValidationError):
        # ai_project_depth max is 40
        ProjectAssessment(
            ai_project_depth=45,
            python_backend=20,
            cloud_fullstack=10,
            engineering_depth=4,
        )

    with pytest.raises(ValidationError):
        # thin_wrapper_penalty max is 15
        ProjectAssessment(
            ai_project_depth=30,
            python_backend=20,
            cloud_fullstack=10,
            engineering_depth=4,
            thin_wrapper_penalty=20,
        )


def test_report_serialization():
    report = ScreeningReport(
        batch_summary=BatchSummary(total_files=1, successfully_parsed=1)
    )
    json_data = report.model_dump_json()
    assert "total_files" in json_data
