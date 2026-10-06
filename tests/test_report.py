import json
from pathlib import Path
from src.models import (
    BatchSummary,
    RankedCandidate,
    ScoreBreakdown,
    ScreeningReport,
)
from src.report import export_json, export_csv, print_terminal_summary


def test_export_json_and_csv_excluding_email(tmp_path: Path):
    candidate = RankedCandidate(
        rank=1,
        candidate_name="Elena Petrova",
        email="elena@example.com",
        total_score=85,
        score_breakdown=ScoreBreakdown(
            ai_project_depth=35,
            python_backend=25,
            cloud_fullstack=12,
            github=8,
            engineering_depth=5,
        ),
        matched_skills=["Python", "FastAPI", "RAG"],
        source_file="resume.pdf",
    )
    report = ScreeningReport(
        batch_summary=BatchSummary(total_files=1, successfully_parsed=1, eligible=1),
        ranked_candidates=[candidate],
    )

    out_json = tmp_path / "results.json"
    export_json(report, out_json, include_email=False)

    with open(out_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Email must be excluded when include_email=False
    assert "email" not in data["ranked_candidates"][0]
    assert data["ranked_candidates"][0]["candidate_name"] == "Elena Petrova"

    # Export CSV
    csv_file = export_csv(report, out_json, include_email=False)
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "Elena Petrova" in content
    assert "elena@example.com" not in content


def test_print_terminal_summary(capsys):
    candidate = RankedCandidate(
        rank=1,
        candidate_name="Test Candidate",
        total_score=80,
        score_breakdown=ScoreBreakdown(
            ai_project_depth=30,
            python_backend=25,
            cloud_fullstack=10,
            github=10,
            engineering_depth=5,
        ),
        source_file="test.pdf",
    )
    report = ScreeningReport(
        batch_summary=BatchSummary(total_files=1, successfully_parsed=1, eligible=1),
        ranked_candidates=[candidate],
    )
    print_terminal_summary(report)
