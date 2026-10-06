from src.eligibility import evaluate_eligibility


def test_js_java_react_only_rejected():
    resume = """
    Alice Williams
    Senior Frontend Engineer
    Skills: JavaScript, TypeScript, React, Next.js, Java, Spring Boot, HTML, CSS.
    Experience: Built responsive web interfaces using React and Java APIs.
    """
    result = evaluate_eligibility(resume, ["React", "Next.js"])
    assert not result.eligible
    assert "No evidence of Python stack" in result.rejection_reasons
    assert "No AI/agentic project evidence" in result.rejection_reasons
    assert not result.needs_review


def test_python_only_without_ai_rejected():
    resume = """
    Bob Martin
    Backend Python Engineer
    Skills: Python, Django, PostgreSQL, Docker, Redis.
    Experience: Designed REST APIs using Django and PostgreSQL.
    """
    result = evaluate_eligibility(resume, ["Python", "Django", "PostgreSQL", "Docker", "Redis"])
    assert not result.eligible
    assert "No AI/agentic project evidence" in result.rejection_reasons
    assert "No evidence of Python stack" not in result.rejection_reasons
    assert not result.needs_review


def test_python_and_langgraph_eligible():
    resume = """
    Carol Chen
    AI Backend Engineer
    Skills: Python, FastAPI, LangGraph, Docker.
    Experience: Implemented multi-agent workflows using LangGraph and Python.
    """
    result = evaluate_eligibility(resume, ["Python", "FastAPI", "LangGraph", "Docker"])
    assert result.eligible
    assert len(result.rejection_reasons) == 0
    assert "python_evidence" in result.evidence_snippets
    assert "ai_evidence" in result.evidence_snippets


def test_generic_ml_only_rejected_and_needs_review():
    resume = """
    David Miller
    Data Scientist
    Skills: Python, Machine Learning, Deep Learning, Data Science.
    Experience: Built predictive machine learning models in scikit-learn.
    """
    result = evaluate_eligibility(resume, ["Python", "Scikit-Learn"])
    assert not result.eligible
    assert result.needs_review
    assert any("generic AI/ML keywords only" in r for r in result.rejection_reasons)


def test_python_js_rag_eligible():
    resume = """
    Elena Rostova
    Fullstack AI Engineer
    Skills: Python, JavaScript, React, RAG, ChromaDB.
    Experience: Built fullstack application with React frontend and Python RAG pipeline.
    """
    result = evaluate_eligibility(resume, ["Python", "React", "RAG", "Chroma"])
    assert result.eligible
    assert len(result.rejection_reasons) == 0


def test_bare_agent_false_positive_prevention():
    resume = """
    Frank Vance
    Real Estate Agent & Python Script Developer
    Skills: Python, Automation.
    Experience: Acted as buyer's agent while writing Python automation scripts.
    Configured user agent headers in HTTP requests.
    """
    result = evaluate_eligibility(resume, ["Python"])
    assert not result.eligible
    # Bare agent must NOT satisfy rule 2
    assert "No AI/agentic project evidence" in result.rejection_reasons
