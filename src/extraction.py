"""Information extraction from parsed resume text."""

import re
from pathlib import Path
from typing import Optional

from src.config import (
    CANONICAL_SKILL_ALIASES,
    GITHUB_RESERVED_USERS,
)
from src.models import ExtractedInfo

EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
GITHUB_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?",
    re.IGNORECASE,
)

SKILLS_HEADINGS = re.compile(
    r"^(?:technical\s+)?(?:skills|competencies|technologies|tools|tech\s+stack|core\s+skills)\b",
    re.IGNORECASE,
)
PROJECTS_EXP_HEADINGS = re.compile(
    r"^(?:work\s+|professional\s+|relevant\s+)?(?:experience|projects|employment|history|work\s+history)\b",
    re.IGNORECASE,
)
OTHER_HEADINGS = re.compile(
    r"^(?:education|certifications|awards|summary|profile|about\s+me|publications)\b",
    re.IGNORECASE,
)


def extract_email(text: str) -> Optional[str]:
    """Extract first valid email address from text."""
    match = EMAIL_REGEX.search(text)
    return match.group(0).lower() if match else None


def extract_github_username(text: str, links: Optional[list[str]] = None) -> Optional[str]:
    """Extract GitHub username, ignoring repo paths, reserved words, and preferring profile links."""
    combined_sources = [text]
    if links:
        combined_sources.extend(links)

    profile_candidates: list[str] = []
    repo_candidates: list[str] = []

    for source in combined_sources:
        for match in GITHUB_URL_REGEX.finditer(source):
            user = match.group(1).strip().strip("/")
            subpath = match.group(2)
            if not user or user.lower() in GITHUB_RESERVED_USERS:
                continue
            # Filter file extensions or git artifacts
            if user.endswith((".git", ".png", ".jpg", ".html")):
                continue
            if not subpath:
                profile_candidates.append(user)
            else:
                repo_candidates.append(user)

    if profile_candidates:
        return profile_candidates[0]
    if repo_candidates:
        return repo_candidates[0]
    return None


def extract_name(text: str, fallback_filename: str) -> str:
    """Best-effort candidate name extraction, falling back to cleaned filename."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:8]:
        # Skip headers, emails, links, phones, and non-name patterns
        lower = line.lower()
        if any(h in lower for h in ("resume", "curriculum vitae", "cv", "page ", "email:", "phone:", "skills", "experience", "projects", "education")):
            continue
        if "@" in line or "http://" in line or "https://" in line or "github.com" in line:
            continue
        if re.search(r"\d{3,}", line):
            continue

        # Strip emojis / non-name characters before checking word lengths
        cleaned = re.sub(r"[^A-Za-z\s.'-]", "", line).strip()
        cleaned_lower = cleaned.lower()
        if any(h in cleaned_lower for h in ("resume", "skills", "experience", "education", "projects")):
            continue

        words = cleaned.split()
        if 2 <= len(words) <= 4 and all(len(w) >= 2 for w in words):
            return cleaned

    # Fallback to cleaned filename
    stem = Path(fallback_filename).stem
    cleaned = re.sub(r"[_\-]+", " ", stem).strip()
    return cleaned.title() if cleaned else "Unknown Candidate"


def detect_sections(text: str) -> dict[str, str]:
    """Classify resume text into sections: skills, projects_experience, or unknown."""
    sections: dict[str, list[str]] = {
        "skills": [],
        "projects_experience": [],
        "unknown": [],
    }
    current_section = "unknown"

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        # Detect section headings (typically short line, often ending in colon or bold-like)
        if len(line_clean) < 40:
            header_test = line_clean.rstrip(":")
            if SKILLS_HEADINGS.match(header_test):
                current_section = "skills"
                continue
            elif PROJECTS_EXP_HEADINGS.match(header_test):
                current_section = "projects_experience"
                continue
            elif OTHER_HEADINGS.match(header_test):
                current_section = "unknown"
                continue

        sections[current_section].append(line_clean)

    return {sec: "\n".join(lines) for sec, lines in sections.items()}


def extract_skills_by_section(
    text: str, sections: dict[str, str]
) -> tuple[list[str], dict[str, list[str]]]:
    """Identify matched skills and which section each skill appears in."""
    matched_skills_set: set[str] = set()
    skills_by_section: dict[str, set[str]] = {
        "skills": set(),
        "projects_experience": set(),
        "unknown": set(),
    }

    # Sort aliases by descending length to match compound terms first (e.g. 'google cloud' before 'google')
    sorted_aliases = sorted(CANONICAL_SKILL_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)

    for alias, canonical in sorted_aliases:
        # For RAG, enforce exact case match \bRAG\b to avoid matching 'rag' inside words or common usage
        if alias == "rag":
            pattern = re.compile(r"\bRAG\b")
        else:
            pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)

        if pattern.search(text):
            matched_skills_set.add(canonical)
            for sec_name, sec_text in sections.items():
                if pattern.search(sec_text):
                    skills_by_section[sec_name].add(canonical)

    matched_skills = sorted(matched_skills_set)
    formatted_by_section = {
        sec: sorted(skills) for sec, skills in skills_by_section.items()
    }
    return matched_skills, formatted_by_section


def extract_candidate_info(
    text: str, source_file: str, links: Optional[list[str]] = None
) -> ExtractedInfo:
    """Extract candidate profile, contacts, GitHub handle, and skills with section mapping."""
    email = extract_email(text)
    github = extract_github_username(text, links)
    name = extract_name(text, source_file)
    sections = detect_sections(text)
    matched_skills, by_section = extract_skills_by_section(text, sections)

    return ExtractedInfo(
        candidate_name=name,
        email=email,
        github_username=github,
        matched_skills=matched_skills,
        skills_by_section=by_section,
    )
