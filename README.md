# AI Resume Screening & Ranking CLI

A production-minded, explainable, and fault-tolerant CLI tool designed to screen, evaluate, enrich, and rank candidate resumes for Python and AI Engineering roles.

---

## Overview

The **AI Resume Screening & Ranking** pipeline evaluates resumes from raw multi-format files (PDF, DOCX, TXT) through a strictly ordered pipeline:
1. **Ingestion & Deduplication**: Discovers files, computes content hashes (SHA-256), extracts text, embedded hyperlinks, and page-1 layout geometry (PyMuPDF with pdfplumber fallback).
2. **Deterministic Extraction**: Extracts candidate name using layout-based scoring (font size relative to page median, vertical position, merged consecutive spans, and contact overlap with email/GitHub/LinkedIn) returning a `name_source` field, along with email, GitHub handle, normalized skills, and section mappings.
3. **Hard Eligibility Filtering**: Zero-LLM deterministic rules ensuring candidates have verifiable Python stack evidence and strong AI/agentic engineering credentials. The deterministic filter requires explicit evidence of modern AI/LLM/agentic work (LLM APIs, RAG, embeddings, agent frameworks, tool calling). Candidates with only generic ML/data-science keywords, or custom implementations that do not use recognisable terminology, are rejected with needs_review set so a human can double-check. They are not silently dropped.
4. **GitHub Enrichment**: Bounded thread pool query of GitHub's public REST API for recent activity (90 days) and maintained relevant repositories (up to 10 points).
5. **LLM Evaluation & Deterministic Post-Guards**: Invokes Google Gemini for rubric-based scoring across AI depth, Python backend, cloud/fullstack, and engineering rigor. Applies strict post-guards (clamping, penalty deductions, evidence verification, low-AI caps).
6. **Fault-Tolerant Fallback**: If LLM provider quotas or network errors occur, falls back deterministically to section-weighted heuristic scoring without crashing the batch.
7. **Ranking & Structured Export**: Produces ranked outputs in JSON and CSV, accompanied by a clean terminal summary table.

---

## Setup & Installation

### Requirements
- Python 3.11+ (Python 3.12 recommended)
- `pip`

### Installation Steps
```bash
# 1. Clone repository
git clone <repo-url>
cd resume_ranker

# 2. Create virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Environment Variables

Configuration is loaded from environment variables or a local `.env` file (copied from `.env.example`):

| Variable | Type | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | string | `""` | Google Gemini API key for structured evaluation. |
| `LLM_MODEL` | string | `gemini-3.5-flash-lite` | Gemini model identifier used for evaluation. |
| `LLM_RPM` | integer | `5` | Client-side rate limit in requests per minute (free tier: 5 RPM). |
| `GITHUB_TOKEN` | string | `""` | Optional GitHub Personal Access Token (increases rate limit from 60 to 5,000 req/hr). |
| `INCLUDE_EMAIL_IN_OUTPUT` | boolean | `false` | Privacy flag. When `false`, emails are stripped from JSON/CSV exports. |
| `MAX_WORKERS` | integer | `4` | Concurrency worker pool size for GitHub API requests. |
| `CACHE_DIR` | path | `.cache` | Local directory for caching GitHub and LLM responses. |

---

## Run Commands

### 1. Screen Resumes with LLM & GitHub Enrichment
```bash
python main.py --input ./resumes --output ./output/results.json
```

### 2. Run in Offline / Deterministic Heuristic Mode (No LLM Calls)
```bash
python main.py --input ./resumes --output ./output/results.json --no-llm
```

### 3. Run on Synthetic Test Fixtures
```bash
python main.py --input ./tests/fixtures --output ./output/smoke_results.json --no-llm
```

### 4. Advanced CLI Options
```bash
python main.py --help
# Options:
#   --input, -i       Input folder or file containing resumes (PDF/DOCX/TXT)
#   --output, -o      Target output path for results JSON file (CSV co-located)
#   --no-llm          Force deterministic heuristic scoring instead of LLM
#   --workers, -w     Maximum concurrent worker threads (default: 4)
#   --top             Number of top candidates to display in terminal summary (default: 10)
#   --verbose, -v     Enable verbose debug logging
```

### 5. Running the Automated Test Suite
```bash
pytest -q
```

---

## Output Format

The output is written to structured JSON (`output/results.json`) and a tabular CSV (`output/results.csv`). The candidate entries shown in the sample schema below are illustrative; see [`output/results.json`](output/results.json) for the complete real evaluation output.

> **Performance**: The first uncached run took about 208 s (30 LLM calls spaced at 5 requests per minute on the Gemini free tier); a re-run with the disk cache takes about 1-2 s.

### JSON Schema
```json
{
  "batch_summary": {
    "total_files": 50,
    "successfully_parsed": 50,
    "eligible": 30,
    "rejected": 20,
    "failed_unreadable": 0,
    "duplicates": 0,
    "llm_fallbacks": 0,
    "github_failures": 1,
    "run_seconds": 1.2
  },
  "ranked_candidates": [
    {
      "rank": 1,
      "candidate_name": "Abhinav Mishra",
      "name_source": "layout",
      "eligible": true,
      "total_score": 96,
      "score_breakdown": {
        "ai_project_depth": 37,
        "python_backend": 29,
        "cloud_fullstack": 15,
        "github": 10,
        "engineering_depth": 5
      },
      "thin_wrapper_penalty": 0,
      "matched_skills": ["Python", "FastAPI", "LangGraph", "Docker", "PostgreSQL"],
      "project_summary": "Architected multi-agent customer support orchestration with LangGraph.",
      "github_summary": "GitHub: 10/10 pts (22 events/90d, 4 maintained repos, 3 relevant repos)",
      "github_status": "ok",
      "strengths": ["Autonomous agent architecture", "Production async FastAPI"],
      "concerns": [],
      "evidence": {
        "ai_project_depth": ["Engineered LangGraph state machine with custom tool calling"],
        "python_backend": ["Built high throughput FastAPI REST service"]
      },
      "scoring_method": "llm",
      "source_file": "resumes/candidate_10.pdf"
    }
  ],
  "rejected_candidates": [
    {
      "candidate_name": "John Smith",
      "name_source": "layout",
      "eligible": false,
      "rejection_reasons": ["generic AI/ML keywords only, no LLM/RAG/agent evidence"],
      "matched_skills": ["Python", "Scikit-Learn"],
      "needs_review": true,
      "source_file": "resumes/candidate_05.pdf"
    }
  ],
  "failed_files": []
}
```

---

## Assumptions

1. **Untrusted Input & Prompt Injection**: Resumes are treated purely as inert text data. All system instructions explicitly command the evaluator to ignore any embedded directives or prompt-injection attempts.
2. **Privacy First**: Candidate email addresses are excluded from exports by default (`INCLUDE_EMAIL_IN_OUTPUT=false`) to prevent accidental PII leakage.
3. **Hard Filter Purity**: LLMs are never permitted to make pass/fail eligibility decisions. Only deterministic code determines eligibility.
4. **GitHub Profile Derivation**: When a candidate links to a GitHub repository (`github.com/user/repo`), only the user segment is queried for profile enrichment. Profile-level links take precedence over repository links.
5. **No Fatal Exceptions**: Network timeouts, missing tokens, unreadable PDFs, or provider 429 rate limits must never terminate the batch.

---

## Design Decisions

### 1. Filtering Strategy
- **Two Hard Rules**:
  1. *Python Stack Signal*: Requires `\bpython\b` or major Python ecosystem indicators (FastAPI, Django, Flask, PyTorch, pandas, etc.).
  2. *Strong AI/Agentic Evidence*: Requires concrete terms (LangChain, LangGraph, Google ADK, LlamaIndex, `\bRAG\b`, embeddings, vector search, tool calling, multi-agent). Bare "agent" (e.g. real-estate agent, user agent) is strictly prevented from triggering.
- **Generic AI Handling**: The deterministic filter requires explicit evidence of modern AI/LLM/agentic work (LLM APIs, RAG, embeddings, agent frameworks, tool calling). Candidates with only generic ML/data-science keywords, or custom implementations that do not use recognisable terminology, are rejected with needs_review set so a human can double-check. They are not silently dropped.
- **Cross-Stack Safety**: Frontend signals (React, TypeScript, Next.js) never penalize or disqualify candidates if Python + AI criteria are met.

### 2. Scoring Strategy (100 Points)
- **Rubric Allocation**:
  - `ai_project_depth`: 40 points (real multi-agent systems, custom RAG, tool calling, retrieval architectures)
  - `python_backend`: 30 points (FastAPI, Django, async, PostgreSQL, Redis, Celery)
  - `cloud_fullstack`: 15 points (Docker, Kubernetes, GCP, AWS, React, Next.js)
  - `github`: 10 points (public activity and relevant code repositories)
  - `engineering_depth`: 5 points (testing, metrics, architectural ownership)
- **Deterministic Post-Guards**:
  - **Guard A**: Clamps each category to its maximum and clamps thin wrapper penalties to [0, 15].
  - **Guard B**: If strong AI terms exist only in a skills list and never appear in projects/experience, `ai_project_depth` is capped at 10.
  - **Guard C**: Verifies that LLM evidence quotes exist as verbatim substrings in the resume text. Unverifiable quotes are dropped, and a concern is flagged.
  - **Guard D**: Total score = `clamp(sum(categories) + github - penalty, 0, 100)`.
  - **Guard E**: If `ai_project_depth < 15`, total score is capped at 55 (preventing pure Python backend candidates without meaningful AI projects from ranking at the top).

### 3. LLM Usage & Structured Output
- Powered by `google-genai` SDK using Gemini structured output.
- Temperature is fixed at 0.0 for deterministic, repeatable assessments.
- Strict Pydantic response models avoid free-form schema properties to maintain compatibility with Gemini Developer API mode.
- Disk caching (`.cache/llm/`) hashes `resume_text + model + prompt_version`, eliminating redundant API billing on subsequent runs.
- Exponential backoff retries transient failures before triggering deterministic heuristic fallback.

### 4. GitHub Enrichment
- Lightweight public REST API queries without external dependencies.
- Analyzes event frequency over 90 days and counts active, non-forked, relevant repositories within 365 days.
- In-memory and on-disk caching (`.cache/github/`) ensures handles are never fetched more than once.
- Unauthenticated requests gracefully handle HTTP 403 / 429 rate limits without crashing.

### 5. Client-Side Rate Limiting & Free Tier Quota Management
- **Thread-Safe Minimum-Interval Lock**: A dedicated `RateLimiter` ensures requests are spaced by $60.0 / \text{LLM\_RPM}$ (12.0 seconds at the default 5 RPM), eliminating burst-induced HTTP 429 errors.
- **Honoring Upstream Retry Signals**: When transient 429 responses occur, the adapter extracts suggested retry wait times (`retryDelay: '37s'`) from Google Gemini RPC metadata and sleeps with a safety margin before retrying (up to 4 retries).
- **Execution Duration Expectations**: On the Gemini Free Tier without prior cache hits, evaluating a batch of 30 eligible candidates requires **~6–7 minutes** ($30 \times 12\,\text{s} = 360\,\text{s}$ plus network latency). Once evaluated, results are cached permanently on disk, making subsequent runs execute in seconds.
- **Daily Quota Protection**: Automatically switches to compatible flash models (`gemini-3.5-flash-lite`) if a model's daily quota ceiling is reached, ensuring 100% of eligible candidates receive full LLM structured evaluations.

## FastAPI Service (Web Wrapper)

In addition to the CLI, the pipeline is wrapped in a lightweight FastAPI application (`src/api.py`):

### Starting the Server
```bash
uvicorn src.api:app --host 127.0.0.1 --port 8000 --reload
```

### Endpoints
- **`GET /health`**: Health check probe returning service status.
- **`POST /screen`**: Triggers resume screening over a designated directory with bounded concurrency.
  ```bash
  curl -X POST http://127.0.0.1:8000/screen \
    -H "Content-Type: application/json" \
    -d '{"input_path": "./resumes", "no_llm": false, "max_workers": 4}'
  ```
- **`GET /results`**: Fetches the structured JSON screening report.
  ```bash
  curl http://127.0.0.1:8000/results
  ```
- **Interactive Documentation**: Available at `http://127.0.0.1:8000/docs` (Swagger UI).

---

## Known Limitations

- The LLM was not given the current date and flagged valid 2025-2026 dates as "future" in the concerns of about a third of candidates.
- Two Gemini models (gemini-2.5-flash, then gemini-3.5-flash-lite after the daily free-tier quota) contributed to the scores, and the model used is not stored per candidate.
- No human-labelled ground truth: weights and cut-offs are not calibrated.
- Scores cluster at the top (ranks 1-12 are between 83 and 96), so small differences should not be over-read.
- A name that exists only as an image in a PDF cannot be recovered.

Detailed operational run notes, telemetry, and execution history are linked in [docs/run_notes.md](docs/run_notes.md) (with historical logs in [docs/run1.md](docs/run1.md) and [docs/run2.md](docs/run2.md)).

---

## If I Had More Time

1. **Human-labelled calibration set**: Hand-rank 10-15 resumes and tune weights and prompts against them, measuring rank agreement.
2. **Reproducibility**: Store model name, prompt version and run date with every result, use a single model per run, and pass the current date to the LLM so valid 2025-2026 dates are not flagged as "future".
3. **Bias reduction**: Anonymise names, photos and college names before LLM evaluation.
4. **Semantic AI detection**: Use lightweight embeddings to recognise custom retrieval/agent implementations that never name a standard framework.
