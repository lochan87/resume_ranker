"""Hard eligibility evaluation using deterministic rules."""

import re
from typing import Optional

from src.config import (
    PYTHON_SIGNALS,
    STRONG_AI_PATTERNS,
    GENERIC_AI_PATTERNS,
)
from src.models import EligibilityResult


def _extract_snippet(text: str, match_span: tuple[int, int], max_words: int = 20) -> str:
    """Extract a short snippet of at most max_words around the match span."""
    start_idx, end_idx = match_span
    # Expand slightly around the match
    left = max(0, start_idx - 100)
    right = min(len(text), end_idx + 100)
    chunk = text[left:right].strip()

    # Replace excessive whitespace/newlines
    clean_chunk = re.sub(r"\s+", " ", chunk)
    words = clean_chunk.split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return clean_chunk


def check_python_evidence(text: str) -> tuple[bool, Optional[str]]:
    """Check for Python language or Python ecosystem signals."""
    for pattern in PYTHON_SIGNALS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            snippet = _extract_snippet(text, match.span())
            return True, snippet
    return False, None


def check_strong_ai_evidence(text: str) -> tuple[bool, Optional[str]]:
    """Check for strong AI/agentic/RAG signals, avoiding bare 'agent'."""
    for pattern in STRONG_AI_PATTERNS:
        # RAG pattern is case-sensitive
        flags = 0 if pattern == r"\bRAG\b" else re.IGNORECASE
        match = re.search(pattern, text, flags)
        if match:
            snippet = _extract_snippet(text, match.span())
            return True, snippet
    return False, None


def check_generic_ai_evidence(text: str) -> bool:
    """Check for presence of generic AI/ML keywords."""
    for pattern in GENERIC_AI_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def evaluate_eligibility(
    text: str, matched_skills: list[str]
) -> EligibilityResult:
    """Evaluate candidate eligibility deterministically without LLM intervention."""
    rejection_reasons: list[str] = []
    evidence_snippets: dict[str, str] = {}
    needs_review = False

    has_python, python_snippet = check_python_evidence(text)
    if has_python and python_snippet:
        evidence_snippets["python_evidence"] = python_snippet
    else:
        rejection_reasons.append("No evidence of Python stack")

    has_strong_ai, ai_snippet = check_strong_ai_evidence(text)
    if has_strong_ai and ai_snippet:
        evidence_snippets["ai_evidence"] = ai_snippet
    else:
        # Distinguish between completely missing AI vs generic AI/ML keywords only
        has_generic_ai = check_generic_ai_evidence(text)
        if has_generic_ai:
            rejection_reasons.append(
                "generic AI/ML keywords only, no LLM/RAG/agent evidence"
            )
            needs_review = True
        else:
            rejection_reasons.append("No AI/agentic project evidence")

    is_eligible = has_python and has_strong_ai

    return EligibilityResult(
        eligible=is_eligible,
        rejection_reasons=rejection_reasons if not is_eligible else [],
        matched_skills=matched_skills,
        evidence_snippets=evidence_snippets,
        needs_review=needs_review,
    )
