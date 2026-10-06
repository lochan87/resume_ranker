from pathlib import Path
import fitz  # PyMuPDF
import docx
import pytest

from src.ingestion import (
    discover_resume_files,
    compute_file_hash,
    extract_pdf_content,
    extract_docx_content,
    extract_txt_content,
    ingest_file,
    ingest_resumes,
)


@pytest.fixture
def temp_fixtures_dir(tmp_path: Path):
    d = tmp_path / "resumes"
    d.mkdir()
    return d


def create_sample_pdf(path: Path, text: str, link_url: str = None):
    doc = fitz.open()
    page = doc.new_page()
    p = fitz.Point(50, 72)
    page.insert_text(p, text, fontsize=12)
    if link_url:
        rect = fitz.Rect(50, 90, 200, 110)
        page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": link_url})
    doc.save(path)
    doc.close()


def create_sample_docx(path: Path, text: str):
    doc = docx.Document()
    doc.add_paragraph(text)
    doc.save(path)


def test_txt_ingestion(temp_fixtures_dir: Path):
    txt_path = temp_fixtures_dir / "candidate.txt"
    txt_path.write_text("John Doe\nPython and LangChain Developer", encoding="utf-8")

    text, links = extract_txt_content(txt_path)
    assert "John Doe" in text
    assert "Python" in text
    assert links == []


def test_pdf_ingestion_with_link(temp_fixtures_dir: Path):
    pdf_path = temp_fixtures_dir / "candidate.pdf"
    github_link = "https://github.com/johndoe"
    create_sample_pdf(pdf_path, "John Doe\nSenior Python Engineer", link_url=github_link)

    text, links = extract_pdf_content(pdf_path)
    assert "John Doe" in text
    assert github_link in links
    assert github_link in text  # Appended in text as requested in spec


def test_docx_ingestion(temp_fixtures_dir: Path):
    docx_path = temp_fixtures_dir / "candidate.docx"
    create_sample_docx(docx_path, "Jane Smith\nFastAPI and Docker specialist")

    text, links = extract_docx_content(docx_path)
    assert "Jane Smith" in text
    assert "FastAPI" in text


def test_deduplication(temp_fixtures_dir: Path):
    file1 = temp_fixtures_dir / "resume1.txt"
    file2 = temp_fixtures_dir / "resume2.txt"
    content = "Identical content for duplicate check"
    file1.write_text(content, encoding="utf-8")
    file2.write_text(content, encoding="utf-8")

    parsed, failures = ingest_resumes(temp_fixtures_dir)
    assert len(failures) == 0
    assert len(parsed) == 2
    originals = [r for r in parsed if not r.is_duplicate]
    duplicates = [r for r in parsed if r.is_duplicate]
    assert len(originals) == 1
    assert len(duplicates) == 1
    assert duplicates[0].duplicate_of == str(file1) or duplicates[0].duplicate_of == str(file2)


def test_corrupted_file_failure(temp_fixtures_dir: Path):
    corrupt_pdf = temp_fixtures_dir / "corrupted.pdf"
    corrupt_pdf.write_bytes(b"%PDF-invalid bytes that cannot be parsed as a real pdf")

    seen_hashes = {}
    parsed, failure = ingest_file(corrupt_pdf, seen_hashes)
    assert parsed is None
    assert failure is not None
    assert "corrupted.pdf" in failure.file


def test_empty_file_failure(temp_fixtures_dir: Path):
    empty_txt = temp_fixtures_dir / "empty.txt"
    empty_txt.write_text("", encoding="utf-8")

    parsed, failure = ingest_file(empty_txt, {})
    assert parsed is None
    assert failure is not None
    assert "empty" in failure.reason.lower()
