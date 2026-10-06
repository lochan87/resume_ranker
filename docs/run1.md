Historical notes, superseded by docs/run_notes.md

# Batch Run Notes: AI Resume Screening & Ranking

This document summarizes the execution results, telemetry, borderline cases, failure modes, and engineering observations from running the screening pipeline over the 50 candidate PDF resumes in `./resumes`.

---

## 1. Batch Execution Statistics

- **Total Files Scanned**: 50
- **Successfully Parsed**: 50 (100% extraction rate)
- **Unreadable / Corrupt Files**: 0
- **Eligible Candidates**: 30 (60.0%)
- **Rejected Candidates**: 20 (40.0%)
- **Identical Duplicates**: 0
- **Scoring Breakdown (Eligible Pool)**:
  - **Full LLM Structured Assessment**: 6 candidates (evaluated via Google Gemini 2.5 Flash)
  - **Deterministic Heuristic Fallback**: 24 candidates (due to free tier RPM quota exhaustion)
- **GitHub Enrichments**:
  - **Successfully Enriched (`ok`)**: 29 candidates
  - **Failed / Not Found (`not_found` / `error`)**: 1 candidate (`github_failures: 1`)
- **Total Pipeline Execution Time**: 62.58 seconds (~1.25s per resume including multi-threaded API calls, retries, and network I/O)

---

## 2. Fallback Analysis: LLM & Heuristic

- **Why Fallbacks Occurred**:
  The evaluation accessed Google Gemini via the `google-genai` SDK using the default free tier key. The Gemini free tier enforces a strict 5 requests-per-minute (RPM) quota on `gemini-2.5-flash`.
- **Fault-Tolerant Behavior**:
  After 2 retries with exponential backoff on HTTP 429 `RESOURCE_EXHAUSTED` responses, the scoring engine smoothly activated the deterministic heuristic fallback (`_compute_heuristic_assessment`), computing structured scores from section-weighted keyword hits.
- **Batch Continuity**:
  Not a single resume crashed the batch. All 30 eligible candidates received complete score breakdowns, category clamping, penalty evaluations, and ranking numbers.

---

## 3. Borderline & `needs_review` Cases

Of the 20 rejected applicants, **16 candidates were flagged with `needs_review: true`**:
- **Pattern**: Candidates possessed generic AI/ML keywords (e.g., "Machine Learning", "Deep Learning", "Data Science", "Scikit-Learn", "Predictive Modeling"), but exhibited **no evidence** of LLM APIs, RAG architectures, agentic systems, LangChain/LangGraph, or vector embeddings.
- **Representative Examples**:
  - `Agam Jain`: Possessed Python and classical Machine Learning coursework, but no modern agentic/LLM project footprint.
  - `Kartikay Sinha`: Flagged for data science and analytics algorithms without Python backend services or generative AI tooling.
  - `VISHWAS BADIGER`: Academic neural network / deep learning background without agentic engineering.
- **Human Recruiter Action**:
  These candidates are separated in `results.json` under `rejected_candidates` with explicit rejection reasons and `needs_review: true`, enabling recruiters to spot candidates who might have unlisted LLM side projects.

---

## 4. Parsing and Extraction Observations

- **PDF Ingestion Success**:
  All 50 PDF resumes were parsed using PyMuPDF (`pymupdf`) with hyperlink extraction (`page.get_links()`). No files required secondary fallbacks or landed in `failed_files`.
- **Hyperlink Extraction Utility**:
  Several candidates (e.g., `candidate_07.pdf`, `candidate_10.pdf`) hid their GitHub profiles behind vector icons or generic "GitHub" anchor text. Hyperlink extraction successfully extracted the underlying `github.com/<username>` target.

---

## 5. GitHub API Reliability

- **Public API Rate Limits**:
  Out of 30 eligible candidates queried against `https://api.github.com`, only 1 profile returned `not_found` (a nonexistent or mistyped handle).
- **Concurrency**:
  Bounded thread execution (`max_workers=4`) kept API latency low while preventing burst rate limit blocking from GitHub's unauthenticated endpoints.
- **Caching**:
  All GitHub profile results were persisted to `.cache/github/<user>.json`, preventing duplicate requests during re-runs.

---

## 6. Weaknesses & Engineering Observations

1. **Heuristic Name Extraction from Styled PDF Layouts**:
   - In multi-column or icon-heavy resumes (e.g., `candidate_35.pdf` and `candidate_30.pdf`), text blocks like `"LinkedIn Github"` or all-caps role titles like `"SOFTWARE ENGINEER"` appeared before the candidate's actual name in the visual stream. While the system fell back to meaningful text, a dedicated layout-aware bounding box parser or targeted regex would improve name precision.
2. **LLM Provider Concurrency & Rate Limit Management**:
   - In production with a tier-limited API, a client-side token-bucket rate limiter (e.g., 5 RPM or 15 RPM limiter) is preferable to waiting for HTTP 429 exceptions and backoff retries. This would ensure higher LLM evaluation density without triggering rate exhaustion.
3. **Section Boundary Ambiguity**:
   - Resumes without explicit section headers (e.g. single-page freeform narratives) categorize all text into `"unknown"`. Although the scoring engine handles `"unknown"` context gracefully, layout-based font-size analysis could enhance section boundary detection.
4. **Keyword Collision in Specialized Terms**:
   - Case-sensitive matching on `\bRAG\b` effectively eliminated false positives with common English words ("rag"), demonstrating the value of precise regex guards over raw string containment.
