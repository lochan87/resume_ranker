from pathlib import Path
from unittest.mock import MagicMock
from src.llm import (
    assess_candidate,
    RateLimiter,
    extract_retry_delay,
)
from src.models import ExtractedInfo, ProjectAssessment


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.current = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.current += seconds


def test_rate_limiter_spacing_with_fake_clock():
    clock = FakeClock()
    # RPM = 5 -> 12.0s interval
    limiter = RateLimiter(rpm=5)

    # 1st call at t=1000 -> immediate
    w1 = limiter.acquire(sleep_fn=clock.sleep, time_fn=clock.time)
    assert w1 == 0.0
    assert len(clock.sleep_calls) == 0

    # 2nd call at t=1002 (2 seconds later) -> should wait 10s
    clock.current = 1002.0
    w2 = limiter.acquire(sleep_fn=clock.sleep, time_fn=clock.time)
    assert w2 == 10.0
    assert clock.sleep_calls == [10.0]
    assert clock.current == 1012.0  # Advanced by 10s

    # 3rd call at t=1030 (18 seconds later) -> elapsed > 12s -> immediate
    clock.current = 1030.0
    w3 = limiter.acquire(sleep_fn=clock.sleep, time_fn=clock.time)
    assert w3 == 0.0
    assert len(clock.sleep_calls) == 1


def test_extract_retry_delay():
    exc1 = RuntimeError("Quota exceeded. Please retry in 37.7107s.")
    assert extract_retry_delay(exc1) == 37.7107

    exc2 = Exception("Rate limit hit: retryDelay': '25s'")
    assert extract_retry_delay(exc2) == 25.0

    exc3 = ValueError("Standard network timeout")
    assert extract_retry_delay(exc3) is None


def test_assess_candidate_honours_retry_delay(tmp_path: Path):
    clock = FakeClock()
    limiter = RateLimiter(rpm=60)
    extracted = ExtractedInfo(candidate_name="Dan", matched_skills=["Python"])

    mock_assessment = ProjectAssessment(
        ai_project_depth=30,
        python_backend=20,
        cloud_fullstack=10,
        engineering_depth=4,
    )

    # Fails once with 429 suggesting 15s retry, then succeeds
    call_count = 0

    def mock_provider(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED: Please retry in 15.0s.")
        return mock_assessment

    res = assess_candidate(
        "Dan resume",
        extracted,
        cache_dir=tmp_path,
        provider_fn=mock_provider,
        rate_limiter=limiter,
        sleep_fn=clock.sleep,
        time_fn=clock.time,
    )

    assert res is not None
    assert call_count == 2
    # 15.0s suggested + 1.0s buffer = 16.0s
    assert any(s >= 15.0 for s in clock.sleep_calls)


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
    )

    provider = MagicMock(return_value=mock_assessment)
    text = "Alice resume with LangChain and Python"

    clock = FakeClock()
    res1 = assess_candidate(
        text,
        extracted,
        cache_dir=tmp_path,
        provider_fn=provider,
        sleep_fn=clock.sleep,
        time_fn=clock.time,
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
        sleep_fn=clock.sleep,
        time_fn=clock.time,
    )
    assert res2 is not None
    assert res2.ai_project_depth == 35
    assert provider.call_count == 1


def test_assess_candidate_retry_and_failure(tmp_path: Path):
    extracted = ExtractedInfo(candidate_name="Charlie", matched_skills=["Python"])
    provider = MagicMock(side_effect=RuntimeError("API quota exceeded"))
    clock = FakeClock()

    res = assess_candidate(
        "Charlie resume text",
        extracted,
        cache_dir=tmp_path,
        provider_fn=provider,
        sleep_fn=clock.sleep,
        time_fn=clock.time,
    )
    assert res is None
    # 5 attempts made (initial + 4 retries)
    assert provider.call_count == 5
