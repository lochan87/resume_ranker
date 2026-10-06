"""Resume ingestion module: discovery, format parsing, link extraction, and deduplication."""

import hashlib
import logging
from pathlib import Path
import re
from typing import Optional
import pymupdf
import pdfplumber
import docx

from src.models import ParsedResume, IngestionFailure

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_pdf_content(path: Path) -> tuple[str, list[str], Optional[list[dict]]]:
    """Extract text, hyperlinks, and page-1 layout spans from PDF using PyMuPDF."""
    text_chunks: list[str] = []
    links: list[str] = []
    layout_spans: list[dict] = []

    doc = None
    try:
        doc = pymupdf.open(path)
        if doc.is_encrypted:
            if not doc.authenticate(""):
                raise ValueError("Encrypted PDF document cannot be read without password")

        if len(doc) > 0:
            p1 = doc[0]
            p_dict = p1.get_text("dict")
            p_h = round(p1.rect.height, 1)
            for b in p_dict.get("blocks", []):
                if "lines" not in b:
                    continue
                for l in b.get("lines", []):
                    spans = l.get("spans", [])
                    if not spans:
                        continue
                    line_parts = [s.get("text", "").strip() for s in spans if s.get("text", "").strip()]
                    if not line_parts:
                        continue
                    line_text = " ".join(line_parts)
                    max_size = max(s.get("size", 0.0) for s in spans)
                    l_bbox = l.get("bbox", spans[0].get("bbox", [0, 0, 0, 0]))
                    layout_spans.append({
                        "text": line_text,
                        "font_size": round(max_size, 2),
                        "x": round(l_bbox[0], 1),
                        "y": round(l_bbox[1], 1),
                        "page_height": p_h,
                    })
                    if len(spans) > 1:
                        for s in spans:
                            stext = s.get("text", "").strip()
                            if stext:
                                s_bbox = s.get("bbox", [0, 0, 0, 0])
                                layout_spans.append({
                                    "text": stext,
                                    "font_size": round(s.get("size", 0.0), 2),
                                    "x": round(s_bbox[0], 1),
                                    "y": round(s_bbox[1], 1),
                                    "page_height": p_h,
                                })
                b_lines = b.get("lines", [])
                if 1 < len(b_lines) <= 3 and b.get("bbox", [0, 0, 0, 0])[1] < p_h / 3.0:
                    b_parts = [" ".join(s.get("text", "").strip() for s in l.get("spans", []) if s.get("text", "").strip()) for l in b_lines]
                    block_text = " ".join(p for p in b_parts if p).strip()
                    b_sizes = [s.get("size", 0.0) for l in b_lines for s in l.get("spans", []) if s.get("text", "").strip()]
                    if block_text and b_sizes:
                        layout_spans.append({"text": block_text, "font_size": round(max(b_sizes), 2), "x": round(b.get("bbox", [0, 0, 0, 0])[0], 1), "y": round(b.get("bbox", [0, 0, 0, 0])[1], 1), "page_height": p_h})

        for page in doc:
            page_text = page.get_text()
            if page_text and page_text.strip():
                text_chunks.append(page_text.strip())

            # Extract hyperlink annotations
            for link in page.get_links():
                uri = link.get("uri")
                if uri and uri.strip():
                    links.append(uri.strip())
        doc.close()
    except ValueError as val_err:
        if doc:
            doc.close()
        raise val_err
    except Exception as exc:
        if doc:
            doc.close()
        logger.warning(f"PyMuPDF failed on {path.name}: {exc}. Trying pdfplumber fallback.")
        text_chunks.clear()

    # Fallback to pdfplumber if PyMuPDF returned no text or errored
    if not text_chunks:
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    p_text = page.extract_text()
                    if p_text and p_text.strip():
                        text_chunks.append(p_text.strip())
        except Exception as exc:
            err_str = str(exc) or exc.__class__.__name__
            if "password" in err_str.lower() or "encrypt" in err_str.lower() or "Password" in exc.__class__.__name__:
                raise ValueError("Encrypted PDF document cannot be read without password") from exc
            raise ValueError(f"Failed to read PDF with pdfplumber fallback: {err_str}") from exc

    raw_text = "\n\n".join(text_chunks).strip()
    meaningful_text = re.sub(r"\(cid:\d+\)", "", raw_text).strip()
    if not meaningful_text:
        raise ValueError("Empty or scanned-image PDF without extractable text")

    # Append extracted hyperlink URLs to raw_text
    if links:
        raw_text += "\n\nExtracted Links:\n" + "\n".join(links)

    return raw_text, links, layout_spans


def extract_docx_content(path: Path) -> tuple[str, list[str], Optional[list[dict]]]:
    """Extract text from DOCX document."""
    try:
        doc = docx.Document(path)
        chunks: list[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_str = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                if row_str:
                    chunks.append(row_str)
        text = "\n\n".join(chunks).strip()
        if not text:
            raise ValueError("DOCX document has no text content")
        return text, [], None
    except Exception as exc:
        raise ValueError(f"Failed to parse DOCX: {exc}") from exc


def extract_txt_content(path: Path) -> tuple[str, list[str], Optional[list[dict]]]:
    """Extract text from TXT file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
        if not text:
            raise ValueError("TXT file is empty")
        return text, [], None
    except Exception as exc:
        raise ValueError(f"Failed to read TXT file: {exc}") from exc


def parse_resume_file(path: Path) -> tuple[str, list[str], Optional[list[dict]]]:
    """Route file parsing by extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_content(path)
    elif ext == ".docx":
        return extract_docx_content(path)
    elif ext == ".txt":
        return extract_txt_content(path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def discover_resume_files(directory: Path | str) -> list[Path]:
    """Recursively discover supported resume files."""
    base = Path(directory)
    if not base.exists() or not base.is_dir():
        return []
    files: list[Path] = [
        p for p in base.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def ingest_file(
    path: Path, seen_hashes: dict[str, str]
) -> tuple[Optional[ParsedResume], Optional[IngestionFailure]]:
    """Ingest a single resume file with hash-based deduplication and error isolation."""
    try:
        file_hash = compute_file_hash(path)
        if file_hash in seen_hashes:
            orig = seen_hashes[file_hash]
            return (
                ParsedResume(
                    source_file=str(path),
                    content_hash=file_hash,
                    raw_text="",
                    is_duplicate=True,
                    duplicate_of=orig,
                ),
                None,
            )

        text, links, layout_spans = parse_resume_file(path)
        seen_hashes[file_hash] = str(path)
        return (
            ParsedResume(
                source_file=str(path),
                content_hash=file_hash,
                raw_text=text,
                links=links,
                layout_spans=layout_spans,
                is_duplicate=False,
            ),
            None,
        )
    except Exception as exc:
        return None, IngestionFailure(file=str(path), reason=str(exc))


def ingest_resumes(
    directory_or_files: Path | str | list[Path],
) -> tuple[list[ParsedResume], list[IngestionFailure]]:
    """Ingest multiple resumes, returning parsed resumes and failures."""
    if isinstance(directory_or_files, list):
        files = directory_or_files
    else:
        files = discover_resume_files(directory_or_files)

    parsed_list: list[ParsedResume] = []
    failures: list[IngestionFailure] = []
    seen_hashes: dict[str, str] = {}

    for file_path in files:
        parsed, failure = ingest_file(file_path, seen_hashes)
        if failure:
            failures.append(failure)
        elif parsed:
            parsed_list.append(parsed)

    return parsed_list, failures
