"""GitHub profile enrichment with caching, bounded concurrency, and error resilience."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Optional
import requests

from src.config import DEFAULT_CONFIG
from src.models import GitHubEnrichment, GitHubStatus

logger = logging.getLogger(__name__)

AI_REPO_KEYWORDS = {
    "ai", "llm", "rag", "agent", "agents", "langchain", "langgraph",
    "llamaindex", "embeddings", "vector", "gpt", "gemini", "claude",
    "retrieval", "prompt", "transformer", "neural", "pytorch",
}


def _get_cache_path(username: str, cache_dir: Path) -> Path:
    safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", username.lower())
    target_dir = cache_dir / "github"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{safe_user}.json"


def _read_from_cache(username: str, cache_dir: Path) -> Optional[GitHubEnrichment]:
    path = _get_cache_path(username, cache_dir)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return GitHubEnrichment.model_validate(data)
        except Exception:
            return None
    return None


def _write_to_cache(username: str, result: GitHubEnrichment, cache_dir: Path) -> None:
    path = _get_cache_path(username, cache_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2)
    except Exception as exc:
        logger.debug(f"Failed to cache GitHub data for {username}: {exc}")


def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _calculate_activity_score(
    events: list[dict], repos: list[dict], now: datetime
) -> tuple[int, int]:
    """Calculate 0-5 activity score based on 90-day public events or recent push."""
    recent_events_count = 0
    relevant_types = {"PushEvent", "PullRequestEvent", "CreateEvent", "IssuesEvent"}

    for ev in events:
        ev_type = ev.get("type", "")
        if ev_type in relevant_types or any(t.lower() in ev_type.lower() for t in ("push", "pullrequest", "create", "issue")):
            created_at = _parse_iso_datetime(ev.get("created_at"))
            if created_at and (now - created_at).days <= 90:
                recent_events_count += 1

    if recent_events_count >= 15:
        return 5, recent_events_count
    elif recent_events_count >= 6:
        return 4, recent_events_count
    elif recent_events_count >= 3:
        return 3, recent_events_count
    elif recent_events_count >= 1:
        return 2, recent_events_count

    # If no recent events visible, check if any non-fork repo was pushed within 180 days
    for repo in repos:
        pushed_at = _parse_iso_datetime(repo.get("pushed_at"))
        if pushed_at and (now - pushed_at).days <= 180:
            return 1, recent_events_count

    return 0, recent_events_count


def _calculate_repo_score(repos: list[dict], now: datetime) -> tuple[int, int, int]:
    """Calculate 0-5 repo score based on maintained and relevant repos."""
    maintained_count = 0
    relevant_count = 0

    for repo in repos:
        if repo.get("fork", False):
            continue
        pushed_at = _parse_iso_datetime(repo.get("pushed_at"))
        if not pushed_at or (now - pushed_at).days > 365:
            continue

        maintained_count += 1
        lang = (repo.get("language") or "").lower()
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        topics = [t.lower() for t in repo.get("topics") or []]

        is_python = lang == "python"
        words = set(re.findall(r"\b\w+\b", f"{name} {desc} " + " ".join(topics)))
        has_ai_keywords = bool(words & AI_REPO_KEYWORDS)

        if is_python or has_ai_keywords:
            relevant_count += 1

    score = min(maintained_count, 3) + min(relevant_count, 2)
    return score, maintained_count, relevant_count


def fetch_github_profile(
    username: Optional[str],
    token: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    session: Optional[requests.Session] = None,
) -> GitHubEnrichment:
    """Fetch and score GitHub activity with error handling and caching."""
    if not username:
        return GitHubEnrichment(
            status=GitHubStatus.NOT_PROVIDED,
            score=0,
            summary="GitHub profile not provided",
        )

    cache = cache_dir or DEFAULT_CONFIG.cache_dir
    cached = _read_from_cache(username, cache)
    if cached:
        return cached

    headers = {
        "User-Agent": "resume-ranker/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    auth_token = token or DEFAULT_CONFIG.github_token
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    http = session or requests.Session()
    now = datetime.now(timezone.utc)

    try:
        events_url = f"https://api.github.com/users/{username}/events/public"
        repos_url = f"https://api.github.com/users/{username}/repos?sort=pushed&per_page=100"

        ev_resp = http.get(events_url, headers=headers, timeout=5.0)
        if ev_resp.status_code == 404:
            res = GitHubEnrichment(
                status=GitHubStatus.NOT_FOUND,
                score=0,
                summary=f"GitHub user '{username}' not found",
            )
            _write_to_cache(username, res, cache)
            return res
        elif ev_resp.status_code in (403, 429):
            return GitHubEnrichment(
                status=GitHubStatus.RATE_LIMITED,
                score=0,
                summary=f"GitHub API rate limit reached for '{username}'",
            )
        elif ev_resp.status_code != 200:
            return GitHubEnrichment(
                status=GitHubStatus.ERROR,
                score=0,
                summary=f"GitHub API error {ev_resp.status_code}",
            )

        repo_resp = http.get(repos_url, headers=headers, timeout=5.0)
        if repo_resp.status_code in (403, 429):
            return GitHubEnrichment(
                status=GitHubStatus.RATE_LIMITED,
                score=0,
                summary=f"GitHub API rate limit reached for '{username}'",
            )
        elif repo_resp.status_code != 200:
            return GitHubEnrichment(
                status=GitHubStatus.ERROR,
                score=0,
                summary=f"GitHub API repos error {repo_resp.status_code}",
            )

        events_data = ev_resp.json() if isinstance(ev_resp.json(), list) else []
        repos_data = repo_resp.json() if isinstance(repo_resp.json(), list) else []

        act_score, ev_count = _calculate_activity_score(events_data, repos_data, now)
        rep_score, maint_count, rel_count = _calculate_repo_score(repos_data, now)
        total_score = min(act_score + rep_score, 10)

        summary = (
            f"GitHub: {total_score}/10 pts ({ev_count} events/90d, "
            f"{maint_count} maintained repos, {rel_count} relevant repos)"
        )

        result = GitHubEnrichment(
            status=GitHubStatus.OK,
            score=total_score,
            activity_score=act_score,
            repo_score=rep_score,
            summary=summary,
            public_events_90d=ev_count,
            maintained_repos=maint_count,
            relevant_repos=rel_count,
        )
        _write_to_cache(username, result, cache)
        return result

    except requests.Timeout:
        return GitHubEnrichment(
            status=GitHubStatus.ERROR,
            score=0,
            summary=f"GitHub request timed out for '{username}'",
        )
    except Exception as exc:
        return GitHubEnrichment(
            status=GitHubStatus.ERROR,
            score=0,
            summary=f"GitHub enrichment failed: {exc}",
        )


def enrich_github_profiles(
    usernames: list[Optional[str]],
    max_workers: int = 4,
    token: Optional[str] = None,
    cache_dir: Optional[Path] = None,
) -> dict[Optional[str], GitHubEnrichment]:
    """Fetch GitHub profiles concurrently with bounded workers."""
    unique_users = {u for u in usernames if u}
    results: dict[Optional[str], GitHubEnrichment] = {
        None: GitHubEnrichment(
            status=GitHubStatus.NOT_PROVIDED,
            score=0,
            summary="GitHub profile not provided",
        )
    }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_github_profile, u, token, cache_dir): u
            for u in unique_users
        }
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                results[u] = fut.result()
            except Exception as exc:
                results[u] = GitHubEnrichment(
                    status=GitHubStatus.ERROR,
                    score=0,
                    summary=f"Worker failure: {exc}",
                )

    return results
