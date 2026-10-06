"""Configuration for AI Resume Screening & Ranking CLI."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from dotenv import load_dotenv

# Load local environment variables from .env if present
load_dotenv()


@dataclass(frozen=True)
class ScoreWeights:
    ai_project_depth: int = 40
    python_backend: int = 30
    cloud_fullstack: int = 15
    github: int = 10
    engineering_depth: int = 5
    max_thin_wrapper_penalty: int = 15


@dataclass(frozen=True)
class ScoringThresholds:
    skills_only_ai_cap: int = 10
    low_ai_depth_threshold: int = 15
    low_ai_depth_total_cap: int = 55
    max_chars_truncate: int = 15000


@dataclass(frozen=True)
class Config:
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)

    # Environment & API settings
    gemini_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    llM_model: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL", "gemini-2.5-flash")
    )
    github_token: str = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", "")
    )
    include_email_in_output: bool = field(
        default_factory=lambda: os.getenv(
            "INCLUDE_EMAIL_IN_OUTPUT", "false"
        ).lower()
        in ("true", "1", "yes")
    )
    max_workers: int = field(
        default_factory=lambda: int(os.getenv("MAX_WORKERS", "4"))
    )
    llm_rpm: int = field(
        default_factory=lambda: int(os.getenv("LLM_RPM", "5"))
    )
    cache_dir: Path = field(
        default_factory=lambda: Path(os.getenv("CACHE_DIR", ".cache"))
    )


# Normalized skills vocabulary mapping: alias (lowercase) -> canonical display name
CANONICAL_SKILL_ALIASES: dict[str, str] = {
    "python": "Python",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "asyncio": "AsyncIO",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "redis": "Redis",
    "docker": "Docker",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "aws": "AWS",
    "amazon web services": "AWS",
    "azure": "Azure",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "google adk": "Google ADK",
    "llamaindex": "LlamaIndex",
    "llama_index": "LlamaIndex",
    "llama-index": "LlamaIndex",
    "rag": "RAG",
    "embeddings": "Embeddings",
    "embedding": "Embeddings",
    "faiss": "FAISS",
    "chroma": "Chroma",
    "chromadb": "Chroma",
    "pinecone": "Pinecone",
    "weaviate": "Weaviate",
    "qdrant": "Qdrant",
    "milvus": "Milvus",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "pandas": "pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "restful": "REST APIs",
    "celery": "Celery",
}

# Strong AI terms required for Hard Eligibility Rule 2
STRONG_AI_PATTERNS: list[str] = [
    r"\blangchain\b",
    r"\blanggraph\b",
    r"\bgoogle\s+adk\b",
    r"\bllamaindex\b",
    r"\bllama[-_]index\b",
    r"\bRAG\b",  # Case-sensitive check handles this specially
    r"\bretrieval[- ]augmented\b",
    r"\bembeddings?\b",
    r"\bvector\s+(search|store|stores|database|databases)\b",
    r"\bfaiss\b",
    r"\bchroma(db)?\b",
    r"\bpinecone\b",
    r"\bweaviate\b",
    r"\btool\s+calling\b",
    r"\bfunction\s+calling\b",
    r"\bmulti[- ]agent\b",
    r"\bagentic\b",
    r"\bai\s+agents?\b",
    r"\bllm\s+agents?\b",
    r"\b(openai|gemini|claude|anthropic|mistral)\s+(api|apis|sdk|models?)\b",
    r"\bprompt\s+engineering\b",
    r"\bllm\s+eval(uation)?s?\b",
]

# Python ecosystem signals for Hard Eligibility Rule 1
PYTHON_SIGNALS: list[str] = [
    r"\bpython\b",
    r"\bfastapi\b",
    r"\bdjango\b",
    r"\bflask\b",
    r"\bpandas\b",
    r"\bnumpy\b",
    r"\bpytorch\b",
    r"\btensorflow\b",
    r"\blangchain\b",
    r"\blanggraph\b",
    r"\bllamaindex\b",
    r"\bgoogle\s+adk\b",
]

# Generic-only AI/ML signals that do not satisfy Rule 2 by themselves
GENERIC_AI_PATTERNS: list[str] = [
    r"\bmachine\s+learning\b",
    r"\bdeep\s+learning\b",
    r"\bdata\s+science\b",
    r"\bartificial\s+intelligence\b",
    r"\bai\b",
    r"\bml\b",
]

# Reserved GitHub paths / usernames to ignore
GITHUB_RESERVED_USERS: set[str] = {
    "features",
    "topics",
    "trending",
    "collections",
    "events",
    "sponsors",
    "security",
    "login",
    "join",
    "pricing",
    "organizations",
    "settings",
    "search",
    "pulls",
    "issues",
    "marketplace",
    "explore",
    "notifications",
    "about",
    "contact",
}

DEFAULT_CONFIG = Config()
