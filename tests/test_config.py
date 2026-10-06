from src.config import DEFAULT_CONFIG, ScoreWeights, CANONICAL_SKILL_ALIASES


def test_weights_sum_to_100():
    w = DEFAULT_CONFIG.weights
    total = (
        w.ai_project_depth
        + w.python_backend
        + w.cloud_fullstack
        + w.github
        + w.engineering_depth
    )
    assert total == 100


def test_aliases_map_to_canonical():
    assert CANONICAL_SKILL_ALIASES["postgres"] == "PostgreSQL"
    assert CANONICAL_SKILL_ALIASES["gcp"] == "GCP"
    assert CANONICAL_SKILL_ALIASES["langchain"] == "LangChain"
