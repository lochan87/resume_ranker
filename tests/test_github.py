from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock
import requests
import pytest

from src.github_enrichment import (
    fetch_github_profile,
    enrich_github_profiles,
    GitHubStatus,
)


@pytest.fixture
def mock_session():
    return MagicMock(spec=requests.Session)


def test_github_not_provided():
    res = fetch_github_profile(None)
    assert res.status == GitHubStatus.NOT_PROVIDED
    assert res.score == 0


def test_github_successful_enrichment(mock_session, tmp_path: Path):
    now = datetime.now(timezone.utc)
    ev_time = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    push_time = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 15 PushEvents in last 90 days
    events_mock = [{"type": "PushEvent", "created_at": ev_time} for _ in range(15)]
    # 3 maintained repos, 2 with Python
    repos_mock = [
        {"fork": False, "pushed_at": push_time, "language": "Python", "name": "ai-agent", "description": ""},
        {"fork": False, "pushed_at": push_time, "language": "Python", "name": "fastapi-service", "description": ""},
        {"fork": False, "pushed_at": push_time, "language": "TypeScript", "name": "frontend", "description": ""},
    ]

    ev_resp = MagicMock()
    ev_resp.status_code = 200
    ev_resp.json.return_value = events_mock

    repo_resp = MagicMock()
    repo_resp.status_code = 200
    repo_resp.json.return_value = repos_mock

    mock_session.get.side_effect = [ev_resp, repo_resp]

    result = fetch_github_profile("octocat", cache_dir=tmp_path, session=mock_session)
    assert result.status == GitHubStatus.OK
    assert result.activity_score == 5
    assert result.repo_score == 5  # min(3,3) + min(2,2) = 5
    assert result.score == 10
    assert "GitHub: 10/10" in result.summary


def test_github_404_not_found(mock_session, tmp_path: Path):
    resp = MagicMock()
    resp.status_code = 404
    mock_session.get.return_value = resp

    result = fetch_github_profile("nonexistent_user_999", cache_dir=tmp_path, session=mock_session)
    assert result.status == GitHubStatus.NOT_FOUND
    assert result.score == 0


def test_github_rate_limited(mock_session, tmp_path: Path):
    resp = MagicMock()
    resp.status_code = 403
    mock_session.get.return_value = resp

    result = fetch_github_profile("limited_user", cache_dir=tmp_path, session=mock_session)
    assert result.status == GitHubStatus.RATE_LIMITED
    assert result.score == 0


def test_github_timeout_handling(mock_session, tmp_path: Path):
    mock_session.get.side_effect = requests.Timeout("Connection timed out")

    result = fetch_github_profile("slow_user", cache_dir=tmp_path, session=mock_session)
    assert result.status == GitHubStatus.ERROR
    assert result.score == 0
    assert "timed out" in result.summary.lower()


def test_github_caching(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    # First write an artificial cache entry
    user_cache = cache_dir / "github" / "cacheduser.json"
    user_cache.parent.mkdir(parents=True)
    user_cache.write_text(
        '{"status": "ok", "score": 8, "activity_score": 4, "repo_score": 4, "summary": "cached", "public_events_90d": 10, "maintained_repos": 2, "relevant_repos": 2}',
        encoding="utf-8",
    )

    # Should hit cache without making network calls
    result = fetch_github_profile("cacheduser", cache_dir=cache_dir)
    assert result.status == GitHubStatus.OK
    assert result.score == 8
    assert result.summary == "cached"


def test_concurrent_enrichment(tmp_path: Path):
    usernames = ["user1", "user2", None]
    results = enrich_github_profiles(usernames, max_workers=2, cache_dir=tmp_path)
    assert None in results
    assert results[None].status == GitHubStatus.NOT_PROVIDED
