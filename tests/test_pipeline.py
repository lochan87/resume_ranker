from pathlib import Path
from src.pipeline import run_screening_pipeline


def test_pipeline_end_to_end_no_llm(tmp_path: Path):
    resumes_dir = tmp_path / "resumes"
    resumes_dir.mkdir()

    # 1. Eligible candidate: Python + LangGraph
    c1 = resumes_dir / "candidate1.txt"
    c1.write_text(
        """Alice Walker
alice@example.com
https://github.com/alicewalker

Technical Skills:
Python, FastAPI, LangGraph, Docker

Work Experience:
Built multi-agent AI system with LangGraph and FastAPI backend.
""",
        encoding="utf-8",
    )

    # 2. Ineligible candidate: Java + React only
    c2 = resumes_dir / "candidate2.txt"
    c2.write_text(
        """Bob Miller
bob@example.com
Technical Skills:
Java, Spring Boot, React, HTML
Work Experience:
Frontend React development.
""",
        encoding="utf-8",
    )

    # 3. Duplicate of candidate1 (identical content)
    c3 = resumes_dir / "candidate3_dup.txt"
    c3.write_text(c1.read_text(encoding="utf-8"), encoding="utf-8")

    # 4. Corrupted file
    c4 = resumes_dir / "corrupt.pdf"
    c4.write_bytes(b"Bad corrupted bytes")

    # 5. Different file with duplicate email of Alice
    c5 = resumes_dir / "candidate5_email_dup.txt"
    c5.write_text(
        """Alice Clone
alice@example.com
Technical Skills: Python, LangChain
Work Experience: AI Engineer
""",
        encoding="utf-8",
    )

    report = run_screening_pipeline(
        resumes_dir,
        no_llm=True,
        max_workers=2,
        cache_dir=tmp_path / "cache",
    )

    bs = report.batch_summary
    assert bs.total_files == 5
    assert bs.successfully_parsed == 4
    assert bs.failed_unreadable == 1
    assert bs.duplicates == 2  # 1 content duplicate + 1 email duplicate
    assert bs.eligible == 1     # Only Alice Walker is eligible
    assert bs.rejected == 3     # Bob + content duplicate + email duplicate
    assert bs.llm_fallbacks == 1

    # Check ranked candidate
    assert len(report.ranked_candidates) == 1
    ranked = report.ranked_candidates[0]
    assert ranked.candidate_name == "Alice Walker"
    assert ranked.rank == 1
    assert ranked.scoring_method == "heuristic_fallback"

    # Check failed files
    assert len(report.failed_files) == 1
    assert "corrupt.pdf" in report.failed_files[0].file
