from pathlib import Path
import pytest
import pymupdf

from src.ingestion import ingest_resumes
from src.pipeline import run_screening_pipeline
from src.extraction import extract_candidate_info
from src.llm import assess_candidate
from src.models import ExtractedInfo


def test_empty_directory(tmp_path: Path):
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    report = run_screening_pipeline(empty_dir, no_llm=True)
    assert report.batch_summary.total_files == 0
    assert report.batch_summary.eligible == 0
    assert report.batch_summary.rejected == 0
    assert len(report.ranked_candidates) == 0
    assert len(report.failed_files) == 0


def test_completely_missing_fields_resume():
    # Only symbols and whitespace, no name, no email, no github, no skills
    text = "!!! ??? +++ ===\n\n   \t  \n12345 67890\n"
    info = extract_candidate_info(text, "mystery_applicant.pdf")
    assert info.candidate_name == "Mystery Applicant"
    assert info.email is None
    assert info.github_username is None
    assert info.matched_skills == []


def test_unicode_and_emojis_in_resume(tmp_path: Path):
    resume_file = tmp_path / "unicode_candidate.txt"
    resume_file.write_text(
        """🚀 Alex Rivera 🤖
alex.rivera@tech.ai
https://github.com/alexrivera-ai

Technical Skills 🛠️:
Python 🐍, FastAPI ⚡, LangChain 🦜, Docker 🐳

Work Experience 💼:
Engineered autonomous AI agent pipelines using Python and LangChain.
Optimized PostgreSQL query latency with Redis caching.
""",
        encoding="utf-8",
    )

    report = run_screening_pipeline(tmp_path, no_llm=True)
    assert report.batch_summary.total_files == 1
    assert report.batch_summary.eligible == 1
    ranked = report.ranked_candidates[0]
    assert "Alex Rivera" in ranked.candidate_name
    assert "Python" in ranked.matched_skills
    assert "LangChain" in ranked.matched_skills


def test_corrupted_pdf_in_batch_does_not_crash(tmp_path: Path):
    # One good resume, one corrupted PDF
    good_file = tmp_path / "valid.txt"
    good_file.write_text(
        """Sara Connor
sara@resistance.org
Skills: Python, LangGraph
Experience: Built autonomous agent system in Python.
""",
        encoding="utf-8",
    )

    bad_pdf = tmp_path / "broken.pdf"
    bad_pdf.write_bytes(b"%PDF-Broken corrupted garbage header %%%%")

    report = run_screening_pipeline(tmp_path, no_llm=True)
    assert report.batch_summary.total_files == 2
    assert report.batch_summary.successfully_parsed == 1
    assert report.batch_summary.failed_unreadable == 1
    assert len(report.failed_files) == 1
    assert "broken.pdf" in report.failed_files[0].file
    assert report.batch_summary.eligible == 1


def test_encrypted_pdf_handling(tmp_path: Path):
    pdf_path = tmp_path / "encrypted.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(50, 72), "Confidential resume text")
    # Save with encryption
    doc.save(
        pdf_path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner123",
        user_pw="user123",
    )
    doc.close()

    parsed, failures = ingest_resumes([pdf_path])
    assert len(failures) == 1
    assert "encrypted" in failures[0].reason.lower()


def test_whitespace_only_pdf(tmp_path: Path):
    pdf_path = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(pymupdf.Point(50, 72), "     \n\t   \n   ")
    doc.save(pdf_path)
    doc.close()

    parsed, failures = ingest_resumes([pdf_path])
    assert len(failures) == 1
    assert "empty" in failures[0].reason.lower()


def test_long_text_truncation(tmp_path: Path):
    huge_text = "Python LangChain developer " * 2000  # ~54,000 characters
    extracted = ExtractedInfo(candidate_name="Long Text Candidate", matched_skills=["Python", "LangChain"])

    # assess_candidate should truncate without error
    result = assess_candidate(huge_text, extracted, no_llm=True)
    assert result is None  # no_llm returns None
