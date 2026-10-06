from src.models import (
    ExtractedInfo,
    GitHubEnrichment,
    GitHubStatus,
    ProjectAssessment,
    ScoreBreakdown,
    RankedCandidate,
)
from src.scoring import (
    assemble_candidate_score,
    rank_candidates,
)


def _base_github():
    return GitHubEnrichment(status=GitHubStatus.OK, score=8, summary="GitHub OK")


def test_guard_thin_wrapper_penalty():
    extracted = ExtractedInfo(
        candidate_name="Dan",
        matched_skills=["Python", "LangChain"],
        skills_by_section={"projects_experience": ["LangChain"]},
    )
    assessment = ProjectAssessment(
        ai_project_depth=30,
        python_backend=20,
        cloud_fullstack=10,
        engineering_depth=4,
        thin_wrapper_penalty=12,
        evidence={},
        project_summary="Basic API calling",
        strengths=[],
        concerns=[],
    )
    text = "Dan resume with LangChain"
    scored = assemble_candidate_score(text, extracted, _base_github(), assessment, "dan.pdf")
    # 30 + 20 + 10 + 8 (gh) + 4 - 12 = 60
    assert scored.total_score == 60
    assert scored.thin_wrapper_penalty == 12


def test_guard_skills_only_ai_caps_at_10():
    # Strong AI term is only in 'skills', NOT in 'projects_experience'
    extracted = ExtractedInfo(
        candidate_name="Emma",
        matched_skills=["Python", "LangChain", "RAG"],
        skills_by_section={"skills": ["LangChain", "RAG"], "projects_experience": ["Python"]},
    )
    assessment = ProjectAssessment(
        ai_project_depth=35,  # Claimed 35 by LLM
        python_backend=25,
        cloud_fullstack=10,
        engineering_depth=4,
        thin_wrapper_penalty=0,
        evidence={},
        project_summary="Python projects",
        strengths=[],
        concerns=[],
    )
    scored = assemble_candidate_score("Emma resume", extracted, _base_github(), assessment, "emma.pdf")
    # Guard B caps ai_project_depth at 10
    assert scored.score_breakdown.ai_project_depth == 10
    # Guard E also triggers because 10 < 15 -> total capped at 55
    assert scored.total_score <= 55


def test_guard_ai_depth_below_15_caps_total_at_55():
    extracted = ExtractedInfo(
        candidate_name="Frank",
        matched_skills=["Python"],
        skills_by_section={"projects_experience": ["Python"]},
    )
    assessment = ProjectAssessment(
        ai_project_depth=12,  # < 15
        python_backend=30,   # Max python
        cloud_fullstack=15,  # Max cloud
        engineering_depth=5, # Max eng
        thin_wrapper_penalty=0,
        evidence={},
        project_summary="Backend heavy",
        strengths=[],
        concerns=[],
    )
    scored = assemble_candidate_score("Frank resume", extracted, _base_github(), assessment, "frank.pdf")
    # Raw total would be 12 + 30 + 15 + 8 + 5 = 70, but capped at 55
    assert scored.total_score == 55


def test_guard_evidence_verification():
    text = "Implemented high throughput FastAPI microservice."
    extracted = ExtractedInfo(
        candidate_name="Grace",
        matched_skills=["FastAPI"],
        skills_by_section={"projects_experience": ["FastAPI"]},
    )
    assessment = ProjectAssessment(
        ai_project_depth=25,
        python_backend=25,
        cloud_fullstack=10,
        engineering_depth=4,
        thin_wrapper_penalty=0,
        evidence={
            "python_backend": [
                "Implemented high throughput FastAPI microservice.",  # Valid verbatim quote
                "Built an unverified imaginary quantum system.",     # Fake quote
            ]
        },
        project_summary="",
        strengths=[],
        concerns=[],
    )
    scored = assemble_candidate_score(text, extracted, _base_github(), assessment, "grace.pdf")
    assert len(scored.evidence["python_backend"]) == 1
    assert "FastAPI" in scored.evidence["python_backend"][0]
    assert "some evidence could not be verified" in scored.concerns


def test_heuristic_fallback_when_assessment_none():
    extracted = ExtractedInfo(
        candidate_name="Henry",
        matched_skills=["Python", "FastAPI", "Docker", "LangChain"],
        skills_by_section={"projects_experience": ["LangChain", "FastAPI"]},
    )
    scored = assemble_candidate_score(
        "Henry resume with LangChain", extracted, _base_github(), None, "henry.pdf"
    )
    assert scored.scoring_method == "heuristic_fallback"
    assert scored.total_score > 0
    assert any("heuristic fallback" in c for c in scored.concerns)


def test_ranking_sort_and_tie_breaking():
    cand1 = RankedCandidate(
        rank=None,
        candidate_name="Zach",
        total_score=80,
        score_breakdown=ScoreBreakdown(ai_project_depth=30, python_backend=25, cloud_fullstack=10, github=10, engineering_depth=5),
        source_file="z.pdf",
    )
    cand2 = RankedCandidate(
        rank=None,
        candidate_name="Adam",
        total_score=80,
        score_breakdown=ScoreBreakdown(ai_project_depth=35, python_backend=25, cloud_fullstack=10, github=5, engineering_depth=5),
        source_file="a.pdf",
    )
    cand3 = RankedCandidate(
        rank=None,
        candidate_name="Bob",
        total_score=90,
        score_breakdown=ScoreBreakdown(ai_project_depth=35, python_backend=25, cloud_fullstack=15, github=10, engineering_depth=5),
        source_file="b.pdf",
    )

    ranked = rank_candidates([cand1, cand2, cand3])
    # 1st is Bob (score 90)
    assert ranked[0].candidate_name == "Bob"
    assert ranked[0].rank == 1
    # For tie at 80: Zach has GitHub score 10 vs Adam has 5 -> Zach is 2nd
    assert ranked[1].candidate_name == "Zach"
    assert ranked[1].rank == 2
    assert ranked[2].candidate_name == "Adam"
    assert ranked[2].rank == 3
