"""Information extraction from parsed resume text."""

import re
import statistics
from pathlib import Path
from typing import Optional

from src.config import CANONICAL_SKILL_ALIASES, GITHUB_RESERVED_USERS
from src.models import ExtractedInfo

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
GITHUB_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?",
    re.IGNORECASE,
)
LINKEDIN_URL_REGEX = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9_.-]+)", re.I)
SKILLS_HEADINGS = re.compile(r"^(?:technical\s+)?(?:skills|competencies|technologies|tools|tech\s+stack|core\s+skills)\b", re.I)
PROJECTS_EXP_HEADINGS = re.compile(r"^(?:work\s+|professional\s+|relevant\s+)?(?:experience|projects|employment|history|work\s+history)\b", re.I)
OTHER_HEADINGS = re.compile(r"^(?:education|certifications|awards|summary|profile|about\s+me|publications)\b", re.I)

REJECT_KEYWORDS = {
    "education", "secondary", "higher", "science", "school", "college", "university", "institute",
    "board", "degree", "bachelor", "b.tech", "btech", "m.tech", "cgpa", "gpa", "percentage", "pcmb",
    "pcm", "cbse", "hsc", "ssc", "class", "objective", "summary", "profile", "portfolio", "contact",
    "skills", "projects", "experience", "internship", "certifications", "achievements", "linkedin",
    "github", "resume", "cv", "curriculum", "vitae", "candidate", "engineer", "developer", "intern",
    "analyst", "scientist", "full stack", "backend", "frontend",
}


def extract_email(text: str) -> Optional[str]:
    """Extract first valid email address from text."""
    match = EMAIL_REGEX.search(text)
    return match.group(0).lower() if match else None


def extract_github_username(text: str, links: Optional[list[str]] = None) -> Optional[str]:
    """Extract GitHub username, ignoring repo paths and reserved words."""
    combined = [text] + (links or [])
    profiles, repos = [], []
    for src in combined:
        for m in GITHUB_URL_REGEX.finditer(src):
            u = m.group(1).strip().strip("/")
            sub = m.group(2)
            if not u or u.lower() in GITHUB_RESERVED_USERS or u.endswith((".git", ".png", ".jpg", ".html")):
                continue
            (repos if sub else profiles).append(u)
    return profiles[0] if profiles else (repos[0] if repos else None)


def extract_linkedin_slug(text: str, links: Optional[list[str]] = None) -> Optional[str]:
    """Extract LinkedIn profile slug from text or hyperlink URLs."""
    for src in [text] + (links or []):
        m = LINKEDIN_URL_REGEX.search(src)
        if m:
            slug = m.group(1).strip().strip("/")
            if slug and slug.lower() not in ("in", "share", "pub"):
                return slug
    return None


def _clean_candidate_line(line: str) -> str:
    cleaned = re.sub(r"^[•\-\|\#\/\:\s]+|[•\-\|\#\/\:\s]+$", "", line)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_hard_reject(line: str) -> bool:
    if "@" in line or re.search(r"\d", line):
        return True
    if re.search(r"(?:https?://|www\.|\.com\b|\.org\b|\.io\b|\.dev\b|\.in\b|\.net\b|github\.com|linkedin\.com)", line, re.I):
        return True
    words = line.split()
    if len(words) < 2 or len(words) > 5:
        return True
    total_letters = sum(len(re.sub(r"[^A-Za-z]", "", w)) for w in words)
    if (total_letters / len(words)) < 3.0:
        return True
    lower = line.lower()
    if "full stack" in lower or "curriculum vitae" in lower:
        return True
    tokens = set(re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", lower))
    for kw in REJECT_KEYWORDS:
        if kw in tokens:
            return True
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        if re.search(pattern, lower):
            return True
    return False


def _derive_slug_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    tokens = [t for t in re.split(r"[._\-]+", raw) if t]
    if 2 <= len(tokens) <= 3 and all(t.isalpha() and len(t) >= 2 for t in tokens):
        return " ".join(tokens).title()
    return None


def _score_line(
    text: str, fsize: Optional[float], med_size: Optional[float],
    y: Optional[float], page_h: Optional[float], lidx: Optional[int],
    contact_parts: list[str],
) -> float:
    score = 0.0
    words = text.split()
    if fsize is not None and med_size is not None:
        score += (fsize - med_size) * 3.5
    if y is not None and page_h is not None and page_h > 0:
        rel_y = y / page_h
        score += 20.0 if rel_y < 0.12 else (12.0 if rel_y < 0.25 else (6.0 if rel_y < 0.35 else 0.0))
    elif lidx is not None:
        score += 20.0 if lidx == 0 else (15.0 if lidx == 1 else (10.0 if lidx < 5 else (5.0 if lidx < 10 else 2.0)))
    if all(re.fullmatch(r"[A-Za-z]+(?:['.-][A-Za-z]+)*[.]?", w) and (w.istitle() or w.isupper() or len(w) <= 2) for w in words):
        score += 12.0
    score += 6.0 if len(words) in (2, 3) else (3.0 if len(words) == 4 else 0.0)
    for w in words:
        wl = w.lower()
        if len(wl) >= 3 and any(len(cp) >= 3 and (wl in cp or cp in wl) for cp in contact_parts):
            score += 25.0
    return score


def extract_name_and_source(
    text: str, fallback_filename: str,
    layout_spans: Optional[list[dict]] = None,
    email: Optional[str] = None, links: Optional[list[str]] = None,
) -> tuple[str, str]:
    """Robust candidate name extraction via layout scoring, text analysis, and fallbacks."""
    email = email or extract_email(text)
    github = extract_github_username(text, links)
    li_slug = extract_linkedin_slug(text, links)
    contact_parts = []
    if email:
        contact_parts.extend(re.findall(r"[a-z]+", email.split("@")[0].lower()))
    if github:
        contact_parts.extend(re.findall(r"[a-z]+", github.lower()))
    if li_slug:
        contact_parts.extend(re.findall(r"[a-z]+", li_slug.lower()))

    candidates: list[tuple[str, str, Optional[float], Optional[float], Optional[float], Optional[int]]] = []
    med_size = 11.0
    if layout_spans:
        sizes = [float(s.get("font_size", 0)) for s in layout_spans if s.get("font_size")]
        if sizes:
            med_size = statistics.median(sizes)
        for s in layout_spans:
            clean = _clean_candidate_line(s.get("text", ""))
            if not _is_hard_reject(clean):
                candidates.append(("layout", clean, s.get("font_size"), s.get("y"), s.get("page_height"), None))

    p1_lines = [_clean_candidate_line(l) for l in text.splitlines() if _clean_candidate_line(l)]
    for idx, line in enumerate(p1_lines[:25]):
        if not _is_hard_reject(line):
            candidates.append(("text", line, None, None, None, idx))

    best_name, best_src, best_score = None, None, 0.0
    for src, ctext, fsize, y, ph, lidx in candidates:
        sc = _score_line(ctext, fsize, med_size, y, ph, lidx, contact_parts)
        if sc > best_score:
            best_score, best_name, best_src = sc, ctext, src

    if best_name and best_score > 0.0:
        return best_name.title() if best_name.isupper() else best_name, best_src

    email_name = _derive_slug_name(email.split("@")[0] if email else None)
    if email_name:
        return email_name, "email"
    li_name = _derive_slug_name(li_slug)
    if li_name:
        return li_name, "linkedin"
    stem_name = re.sub(r"[_\-]+", " ", Path(fallback_filename).stem).strip().title()
    return stem_name or "Unknown Candidate", "filename"


def extract_name(
    text: str, fallback_filename: str,
    layout_spans: Optional[list[dict]] = None,
    email: Optional[str] = None, links: Optional[list[str]] = None,
) -> str:
    name, _ = extract_name_and_source(text, fallback_filename, layout_spans, email, links)
    return name


def detect_sections(text: str) -> dict[str, str]:
    """Classify resume text into sections: skills, projects_experience, or unknown."""
    sections = {"skills": [], "projects_experience": [], "unknown": []}
    curr = "unknown"
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        if len(line_clean) < 40:
            hdr = line_clean.rstrip(":")
            if SKILLS_HEADINGS.match(hdr):
                curr = "skills"
                continue
            elif PROJECTS_EXP_HEADINGS.match(hdr):
                curr = "projects_experience"
                continue
            elif OTHER_HEADINGS.match(hdr):
                curr = "unknown"
                continue
        sections[curr].append(line_clean)
    return {k: "\n".join(v) for k, v in sections.items()}


def extract_skills_by_section(
    text: str, sections: dict[str, str]
) -> tuple[list[str], dict[str, list[str]]]:
    """Identify matched skills and which section each skill appears in."""
    matched: set[str] = set()
    by_sec = {"skills": set(), "projects_experience": set(), "unknown": set()}
    sorted_aliases = sorted(CANONICAL_SKILL_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, canonical in sorted_aliases:
        pat = re.compile(r"\bRAG\b") if alias == "rag" else re.compile(r"\b" + re.escape(alias) + r"\b", re.I)
        if pat.search(text):
            matched.add(canonical)
            for sname, stext in sections.items():
                if pat.search(stext):
                    by_sec[sname].add(canonical)
    return sorted(matched), {k: sorted(v) for k, v in by_sec.items()}


def extract_candidate_info(
    text: str, source_file: str,
    links: Optional[list[str]] = None,
    layout_spans: Optional[list[dict]] = None,
) -> ExtractedInfo:
    """Extract candidate profile, contacts, GitHub handle, and skills with section mapping."""
    email = extract_email(text)
    github = extract_github_username(text, links)
    name, name_source = extract_name_and_source(text, source_file, layout_spans=layout_spans, email=email, links=links)
    sections = detect_sections(text)
    matched_skills, by_section = extract_skills_by_section(text, sections)
    return ExtractedInfo(
        candidate_name=name,
        name_source=name_source,
        email=email,
        github_username=github,
        matched_skills=matched_skills,
        skills_by_section=by_section,
    )
