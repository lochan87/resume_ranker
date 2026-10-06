from pathlib import Path
from unittest.mock import MagicMock
from src.llm import assess_candidate
from src.models import ExtractedInfo, ProjectAssessment


def test_assess_candidate_no_llm():
    extracted = ExtractedInfo(candidate_name="Bob", matched_skills=["Python"])
    result = assess_candidate("sample text", extracted, no_llm=True)
    assert result is None


def test_assess_candidate_success_and_caching(tmp_path: Path):
    extracted = ExtractedInfo(
        candidate_name="Alice",
        matched_skills=["Python", "FastAPI", "LangChain"],
    )
    mock_assessment = ProjectAssessment(
        ai_project_depth=35,
        python_backend=25,
        cloud_fullstack=12,
        engineering_depth=4,
        thin_wrapper_penalty=0,
        evidence={"ai_project_depth": ["Built LangChain agent with tool calling"]},
        project_summary="Built LangChain multi-agent system with FastAPI.",
        strengths=["Agentic workflows"],
        concerns=[],
    )

    provider = MagicMock(return_value=mock_assessment)
    text = "Alice resume with LangChain and Python"

    # 1st call executes provider
    res1 = assess_candidate(
        text,
        extracted,
        cache_dir=tmp_path,
        provider_fn=provider,
    )
    assert res1 is not None
    assert res1.ai_project_depth == 35
    assert provider.call_count == 1

    # 2nd call hits cache without calling provider again
    res2 = assess_candidate(
        text,
        extracted,
        cache_dir=tmp_path,
        provider_fn=provider,
    )
    assert res2 is not None
    assert res2.ai_project_depth == 35
    assert provider.call_count == 1  # Unchanged!


def test_assess_candidate_retry_and_failure(tmp_path: Path):
    extracted = ExtractedInfo(candidate_name="Charlie", matched_skills=["Python"])
    provider = MagicMock(side_effect=RuntimeError("API quota exceeded"))

    res = assess_candidate(
        "Charlie resume text",
        extracted,
        cache_dir=tmp_path,
        provider_fn=provider,
    )
    assert res is None
    # 3 attempts made (initial + 2 retries)
    assert provider.call_count == 3
