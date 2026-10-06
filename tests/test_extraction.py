from src.extraction import (
    extract_email,
    extract_github_username,
    extract_name,
    detect_sections,
    extract_skills_by_section,
    extract_candidate_info,
)


def test_email_extraction():
    text = "Candidate Alex Smith\nContact: alex.smith@example.com\nPhone: 12345"
    assert extract_email(text) == "alex.smith@example.com"
    assert extract_email("No email here") is None


def test_github_extraction_profile_and_repo():
    # Profile link
    assert extract_github_username("https://github.com/alexsmith") == "alexsmith"
    # Repo link extracts user part only
    assert extract_github_username("https://github.com/alexsmith/fastapi-rag") == "alexsmith"
    # Reserved words ignored
    assert extract_github_username("https://github.com/topics/python") is None
    # Prefer profile link over repo link
    text = "Check out https://github.com/alexsmith/repo and profile https://github.com/alexsmith"
    assert extract_github_username(text) == "alexsmith"
    # From links parameter
    assert extract_github_username("No text link", links=["https://github.com/devuser"]) == "devuser"


def test_name_extraction():
    text = "Johnathan Doe\nSoftware Engineer\njohn@example.com"
    assert extract_name(text, "fallback.pdf") == "Johnathan Doe"

    # Problem patterns appearing above real name
    text_with_linkedin = """
    LinkedIn  Github
    Candidate Portfolio
    Ananya Sharma
    ananya@example.com
    Software Developer
    """
    assert extract_name(text_with_linkedin, "cand_35.pdf") == "Ananya Sharma"

    text_with_job_title = """
    SOFTWARE ENGINEER
    Backend Developer
    Rohan Verma
    rohan@example.com
    """
    assert extract_name(text_with_job_title, "cand_30.pdf") == "Rohan Verma"

    # Fallback to filename
    ugly_text = "Curriculum Vitae\nPage 1\nhttp://link.com"
    assert extract_name(ugly_text, "candidate_07.pdf") == "Candidate 07"


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
    # 'RAG' matches
    text_with_rag = "Engineered RAG pipelines with Pinecone"
    info = extract_candidate_info(text_with_rag, "cand.txt")
    assert "RAG" in info.matched_skills

    # lowercase 'rag' should not match
    text_with_lowercase = "Used a rag to clean the desk and studied python"
    info2 = extract_candidate_info(text_with_lowercase, "cand.txt")
    assert "RAG" not in info2.matched_skills
    assert "Python" in info2.matched_skills
