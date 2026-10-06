"""Pydantic schemas and data models for AI Resume Screening & Ranking."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class GitHubStatus(str, Enum):
    OK = "ok"
    NOT_PROVIDED = "not_provided"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class ScoringMethod(str, Enum):
    LLM = "llm"
    HEURISTIC_FALLBACK = "heuristic_fallback"


class ParsedResume(BaseModel):
    source_file: str
    content_hash: str
    raw_text: str
    links: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


class IngestionFailure(BaseModel):
    file: str
    reason: str


class ExtractedInfo(BaseModel):
    candidate_name: str
    email: Optional[str] = None
    github_username: Optional[str] = None
    matched_skills: list[str] = Field(default_factory=list)
    skills_by_section: dict[str, list[str]] = Field(default_factory=dict)


class EligibilityResult(BaseModel):
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    evidence_snippets: dict[str, str] = Field(default_factory=dict)
    needs_review: bool = False


class GitHubEnrichment(BaseModel):
    status: GitHubStatus
    score: int = Field(ge=0, le=10, default=0)
    activity_score: int = Field(ge=0, le=5, default=0)
    repo_score: int = Field(ge=0, le=5, default=0)
    summary: str = ""
    public_events_90d: int = 0
    maintained_repos: int = 0
    relevant_repos: int = 0


class ProjectAssessment(BaseModel):
    """LLM structured response output model."""

    ai_project_depth: int = Field(
        ge=0, le=40, description="Depth of real AI/agentic/RAG systems (0-40)"
    )
    python_backend: int = Field(
        ge=0, le=30, description="Python backend engineering depth (0-30)"
    )
    cloud_fullstack: int = Field(
        ge=0, le=15, description="Cloud, infrastructure & fullstack signals (0-15)"
    )
    engineering_depth: int = Field(
        ge=0, le=5, description="General software engineering rigor & quality (0-5)"
    )
    thin_wrapper_penalty: int = Field(
        ge=0, le=15, default=0, description="Penalty for thin wrappers/tutorials (0-15)"
    )
    evidence: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Verifiable quotes from resume per category",
    )
    project_summary: str = Field(
        default="", description="1-2 sentences summarizing relevant projects"
    )
    strengths: list[str] = Field(
        default_factory=list, description="Key candidate strengths"
    )
    concerns: list[str] = Field(
        default_factory=list, description="Red flags or gaps"
    )


class ScoreBreakdown(BaseModel):
    ai_project_depth: int = Field(ge=0, le=40)
    python_backend: int = Field(ge=0, le=30)
    cloud_fullstack: int = Field(ge=0, le=15)
    github: int = Field(ge=0, le=10)
    engineering_depth: int = Field(ge=0, le=5)


class RankedCandidate(BaseModel):
    rank: Optional[int] = None
    candidate_name: str
    email: Optional[str] = None
    eligible: bool = True
    total_score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    thin_wrapper_penalty: int = Field(ge=0, le=15, default=0)
    matched_skills: list[str] = Field(default_factory=list)
    project_summary: str = ""
    github_summary: str = ""
    github_status: str = "not_provided"
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    scoring_method: str = "llm"
    source_file: str


class RejectedCandidate(BaseModel):
    candidate_name: str
    email: Optional[str] = None
    eligible: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    needs_review: bool = False
    source_file: str


class BatchSummary(BaseModel):
    total_files: int = 0
    successfully_parsed: int = 0
    eligible: int = 0
    rejected: int = 0
    failed_unreadable: int = 0
    duplicates: int = 0
    llm_fallbacks: int = 0
    github_failures: int = 0
    run_seconds: float = 0.0


class ScreeningReport(BaseModel):
    batch_summary: BatchSummary
    ranked_candidates: list[RankedCandidate] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    failed_files: list[IngestionFailure] = Field(default_factory=list)
