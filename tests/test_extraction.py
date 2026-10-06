import pytest
from src.extraction import (
    extract_email,
    extract_github_username,
    extract_linkedin_slug,
    extract_name,
    extract_name_and_source,
    detect_sections,
    extract_skills_by_section,
    extract_candidate_info,
)


def test_email_extraction():
    text = "Candidate Alex Smith\nContact: alex.smith@example.com\nPhone: 12345"
    assert extract_email(text) == "alex.smith@example.com"
    assert extract_email("No email here") is None


def test_github_extraction_profile_and_repo():
    assert extract_github_username("https://github.com/alexsmith") == "alexsmith"
    assert extract_github_username("https://github.com/alexsmith/fastapi-rag") == "alexsmith"
    assert extract_github_username("https://github.com/topics/python") is None
    text = "Check out https://github.com/alexsmith/repo and profile https://github.com/alexsmith"
    assert extract_github_username(text) == "alexsmith"
    assert extract_github_username("No text link", links=["https://github.com/devuser"]) == "devuser"


def test_linkedin_slug_extraction():
    assert extract_linkedin_slug("Visit https://linkedin.com/in/jane-doe for more") == "jane-doe"
    assert extract_linkedin_slug("No link", links=["https://www.linkedin.com/in/alex_smith/"]) == "alex_smith"


def test_education_line_skipped():
    text = """
    Higher Secondary Science- PCMB
    Pre-University College of Science
    Aarav Mehta
    aarav.mehta@example.com
    Software Developer
    """
    name, source = extract_name_and_source(text, "cand_21.pdf")
    assert name == "Aarav Mehta"
    assert source == "text"


def test_social_and_portfolio_lines_skipped():
    text = """
    LinkedIn Github
    Candidate Portfolio
    Ananya Sharma
    ananya@example.com
    """
    name, source = extract_name_and_source(text, "cand_35.pdf")
    assert name == "Ananya Sharma"


def test_name_split_across_spans():
    layout_spans = [
        {"text": "Vikram Malhotra", "font_size": 22.0, "x": 40.0, "y": 30.0, "page_height": 800.0},
        {"text": "Software Engineer", "font_size": 12.0, "x": 40.0, "y": 60.0, "page_height": 800.0},
    ]
    text = "Software Engineer\nPython FastAPI\nemail: test@example.com"
    name, source = extract_name_and_source(text, "cand_test.pdf", layout_spans=layout_spans)
    assert name == "Vikram Malhotra"
    assert source == "layout"


def test_email_fallback_name():
    ugly_text = """
    Software Engineer Developer Intern
    Education Degree B.Tech CGPA 9.0
    Skills Python FastAPI
    Contact: jane.doe@example.com
    """
    name, source = extract_name_and_source(ugly_text, "unknown_resume.pdf")
    assert name == "Jane Doe"
    assert source == "email"


def test_all_caps_name_title_cased():
    text = """
    KAVITA RAMAN
    Full Stack Developer
    kavita@example.com
    """
    name, source = extract_name_and_source(text, "cand_caps.pdf")
    assert name == "Kavita Raman"


def test_filename_fallback_when_nothing_works():
    ugly_text = """
    Curriculum Vitae Resume
    Software Engineer Developer Intern
    Contact user123@example.com
    """
    name, source = extract_name_and_source(ugly_text, "candidate_35.pdf")
    assert name == "Candidate 35"
    assert source == "filename"


def test_section_and_skills_detection():
    resume_text = """
Jane Doe
jane@example.com

Technical Skills:
Python, PostgreSQL, Docker, Redis

Work Experience:
Software Engineer at Acme
- Built scalable microservices with FastAPI and LangGraph
- Deployed on GCP
"""
    sections = detect_sections(resume_text)
    assert "skills" in sections
    assert "projects_experience" in sections

    matched, by_sec = extract_skills_by_section(resume_text, sections)
    assert "Python" in matched
    assert "FastAPI" in matched
    assert "PostgreSQL" in matched
    assert "LangGraph" in matched
    assert "GCP" in matched
    assert "PostgreSQL" in by_sec["skills"]
    assert "LangGraph" in by_sec["projects_experience"]


def test_rag_case_sensitivity():
    text_with_rag = "Engineered RAG pipelines with Pinecone"
    info = extract_candidate_info(text_with_rag, "cand.txt")
    assert "RAG" in info.matched_skills

    text_with_lowercase = "Used a rag to clean the desk and studied python"
    info2 = extract_candidate_info(text_with_lowercase, "cand.txt")
    assert "RAG" not in info2.matched_skills
    assert "Python" in info2.matched_skills
