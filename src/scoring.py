"""Scoring engine: deterministic guards, penalties, heuristic fallback, and candidate ranking."""

import re
from typing import Optional

from src.config import DEFAULT_CONFIG, STRONG_AI_PATTERNS
from src.models import (
    ExtractedInfo,
    GitHubEnrichment,
    ProjectAssessment,
    ScoreBreakdown,
    RankedCandidate,
    ScoringMethod,
)


def _normalize_text_for_search(text: str) -> str:
    """Normalize text by lowercasing and stripping non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _verify_evidence_quotes(
    evidence: dict[str, list[str]], resume_text: str
) -> tuple[dict[str, list[str]], bool]:
    """Filter evidence quotes that do not exist as normalized substrings in the resume."""
    norm_resume = _normalize_text_for_search(resume_text)
    verified_evidence: dict[str, list[str]] = {}
    dropped_any = False

    for category, quotes in evidence.items():
        kept_quotes: list[str] = []
        for quote in quotes:
            norm_quote = _normalize_text_for_search(quote)
            if norm_quote and norm_quote in norm_resume:
                kept_quotes.append(quote)
            else:
                dropped_any = True
        verified_evidence[category] = kept_quotes

    return verified_evidence, dropped_any


def _has_ai_in_projects(extracted: ExtractedInfo) -> bool:
    """Check if strong AI terms appear in projects/experience."""
    proj_skills = set(extracted.skills_by_section.get("projects_experience", []))
    for p in STRONG_AI_PATTERNS:
        # Check against matched skill names or terms
        for s in proj_skills:
            if re.search(p, s, re.IGNORECASE):
                return True
    return False


def _compute_heuristic_assessment(
    text: str, extracted: ExtractedInfo
) -> ProjectAssessment:
    """Deterministic score fallback when LLM is disabled or unavailable."""
    sec = extracted.skills_by_section
    proj_skills = set(sec.get("projects_experience", []))
    skills_only = set(sec.get("skills", []))
    unknown_skills = set(sec.get("unknown", []))

    # 1. AI project depth (max 40)
    ai_terms = {"LangChain", "LangGraph", "LlamaIndex", "Google ADK", "RAG", "Embeddings", "FAISS", "Chroma", "Pinecone", "Weaviate"}
    ai_in_proj = proj_skills & ai_terms
    ai_in_skills = skills_only & ai_terms
    ai_in_unk = unknown_skills & ai_terms

    ai_score = len(ai_in_proj) * 12 + len(ai_in_unk) * 6 + len(ai_in_skills) * 3
    if not ai_in_proj and (ai_in_skills or ai_in_unk):
        ai_score = min(ai_score, 10)
    ai_score = min(max(ai_score, 0), 40)

    # 2. Python backend (max 30)
    py_terms = {"Python", "FastAPI", "Django", "Flask", "PostgreSQL", "Redis", "AsyncIO", "Celery"}
    py_in_proj = proj_skills & py_terms
    py_in_other = (skills_only | unknown_skills) & py_terms
    py_score = len(py_in_proj) * 8 + len(py_in_other) * 4
    py_score = min(max(py_score, 5), 30)

    # 3. Cloud / fullstack (max 15)
    cloud_terms = {"Docker", "Kubernetes", "GCP", "AWS", "Azure", "React", "Next.js"}
    cloud_hits = (proj_skills | skills_only | unknown_skills) & cloud_terms
    cloud_score = min(len(cloud_hits) * 4, 15)

    # 4. Engineering depth (max 5)
    eng_score = 4 if ("Docker" in extracted.matched_skills or "PostgreSQL" in extracted.matched_skills) else 2

    return ProjectAssessment(
        ai_project_depth=ai_score,
        python_backend=py_score,
        cloud_fullstack=cloud_score,
        engineering_depth=eng_score,
        thin_wrapper_penalty=0,
        evidence={},
        project_summary=f"Technical experience with {', '.join(extracted.matched_skills[:4])}.",
        strengths=[f"Skills identified: {', '.join(extracted.matched_skills[:5])}"],
        concerns=["Score computed via heuristic fallback (LLM evaluation unavailable)."],
    )


def assemble_candidate_score(
    text: str,
    extracted: ExtractedInfo,
    github: GitHubEnrichment,
    assessment: Optional[ProjectAssessment],
    source_file: str,
) -> RankedCandidate:
    """Apply deterministic guards A-E, verify evidence quotes, and assemble final score."""
    is_fallback = assessment is None
    scoring_method = (
        ScoringMethod.HEURISTIC_FALLBACK.value
        if is_fallback
        else ScoringMethod.LLM.value
    )

    if assessment is None:
        assessment = _compute_heuristic_assessment(text, extracted)

    # Guard A: Clamp category scores & penalty
    w = DEFAULT_CONFIG.weights
    ai_depth = min(max(assessment.ai_project_depth, 0), w.ai_project_depth)
    py_backend = min(max(assessment.python_backend, 0), w.python_backend)
    cloud_fs = min(max(assessment.cloud_fullstack, 0), w.cloud_fullstack)
    eng_depth = min(max(assessment.engineering_depth, 0), w.engineering_depth)
    penalty = min(max(assessment.thin_wrapper_penalty, 0), w.max_thin_wrapper_penalty)
    gh_score = min(max(github.score, 0), w.github)

    # Guard B: AI terms ONLY in skills list (not in projects) -> cap at 10
    if not _has_ai_in_projects(extracted):
        ai_depth = min(ai_depth, DEFAULT_CONFIG.thresholds.skills_only_ai_cap)

    # Guard C: Evidence verification against resume text
    verified_evidence, dropped_any = _verify_evidence_quotes(assessment.evidence, text)
    concerns = list(assessment.concerns)
    if dropped_any:
        concerns.append("some evidence could not be verified")

    # Guard D: Total score calculation and clamp
    raw_total = ai_depth + py_backend + cloud_fs + gh_score + eng_depth - penalty
    total = int(min(max(raw_total, 0), 100))

    # Guard E: If ai_project_depth < 15, cap total score at 55
    if ai_depth < DEFAULT_CONFIG.thresholds.low_ai_depth_threshold:
        total = min(total, DEFAULT_CONFIG.thresholds.low_ai_depth_total_cap)

    breakdown = ScoreBreakdown(
        ai_project_depth=ai_depth,
        python_backend=py_backend,
        cloud_fullstack=cloud_fs,
        github=gh_score,
        engineering_depth=eng_depth,
    )

    return RankedCandidate(
        rank=None,
        candidate_name=extracted.candidate_name,
        email=extracted.email,
        eligible=True,
        total_score=total,
        score_breakdown=breakdown,
        thin_wrapper_penalty=penalty,
        matched_skills=extracted.matched_skills,
        project_summary=assessment.project_summary,
        github_summary=github.summary,
        github_status=github.status.value,
        strengths=assessment.strengths,
        concerns=concerns,
        evidence=verified_evidence,
        scoring_method=scoring_method,
        source_file=source_file,
    )


def rank_candidates(candidates: list[RankedCandidate]) -> list[RankedCandidate]:
    """Sort candidates by total_score desc; ties -> github score desc, ai_project_depth desc, name asc."""
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            -c.total_score,
            -c.score_breakdown.github,
            -c.score_breakdown.ai_project_depth,
            c.candidate_name.lower(),
        ),
    )
    for idx, cand in enumerate(sorted_candidates, start=1):
        cand.rank = idx
    return sorted_candidates
