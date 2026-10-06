Historical notes, superseded by docs/run_notes.md

# Batch Run Notes: AI Resume Screening & Ranking (Production Run)

This document provides a comprehensive post-run analysis of the resume screening and ranking pipeline across the 50 candidate PDF resumes in `./resumes`, detailing telemetry, rate-limiting behavior, name extraction improvements, and a before/after comparison between heuristic fallback and full LLM evaluation.

---

## 1. Updated Batch Execution Statistics

- **Total Files Scanned**: 50
- **Successfully Parsed**: 50 (100% ingestion rate via PyMuPDF)
- **Unreadable / Corrupt Files**: 0
- **Eligible Candidates**: 30 (60.0%)
- **Rejected Candidates**: 20 (40.0%)
- **Identical Duplicates**: 0
- **Scoring Method Distribution (Eligible Pool)**:
  - **Full LLM Structured Output (`llm`)**: **30 / 30 (100%)**
  - **Heuristic Fallback (`heuristic_fallback`)**: **0 (0.0%)**
- **GitHub Enrichments**:
  - **Active / OK (`ok`)**: 29 candidates
  - **Missing / Not Found (`not_found` / `error`)**: 1 candidate
- **Total Pipeline Execution Time**: 208.29s (~6.9s per candidate, fully governed by the client-side rate limiter and disk caching)

---

## 2. Client-Side Rate Limiter & Quota Switchover

### The Problem in Run 1
In the initial baseline run, 24 of the 30 eligible candidates fell back to deterministic heuristic scoring because Google Gemini's Free Tier strictly enforces a 5 requests-per-minute (RPM) quota on `gemini-2.5-flash`. When multiple parallel worker threads submitted requests simultaneously, HTTP 429 `RESOURCE_EXHAUSTED` errors were triggered, exhausting backoff attempts.

### The Solution in Run 2
1. **Thread-Safe Rate Limiter (`RateLimiter`)**:
   - Implemented in `src/llm.py` with configurable `LLM_RPM` (default: 5).
   - Guarantees an exact minimum interval ($60.0 / \text{RPM} = 12.0\,\text{s}$) between successive API calls across all threads.
2. **Honoring API Retry Delays**:
   - Added regex extraction for API-suggested wait times (e.g. `retryDelay: '37s'`) from Google Gemini RPC exception payloads, adding a 1-second safety buffer.
3. **Daily Quota Switchover**:
   - In addition to per-minute rate limits, `gemini-2.5-flash` enforces a 20 request-per-day (RPD) free-tier limit.
   - When the daily ceiling was encountered, the adapter automatically switched subsequent requests to `gemini-3.5-flash-lite`, which possesses fresh daily quota and full structured JSON output support.
4. **Cache Reusability**:
   - The on-disk cache in `.cache/llm/` saved all successful LLM assessments. Reruns immediately reused previously verified assessments, making repeated executions faster and zero-cost.

---

## 3. Name Extraction Improvements

In the initial run, multi-column and icon-heavy resumes produced false candidate names:
- `candidate_30.pdf` was incorrectly named `"SOFTWARE ENGINEER"`.
- `candidate_35.pdf` was incorrectly named `"LinkedIn Github"`.

### Algorithmic Refinement
In `src/extraction.py`:
- Explicitly skips lines containing header and metadata keywords (`linkedin`, `github`, `email`, `phone`, `resume`, `cv`, `curriculum`, `vitae`, `candidate`, `portfolio`, `profile`, `software engineer`, `developer`, `intern`, `education`, `experience`, `projects`, `skills`).
- Skips lines containing `@`, digits, or web URLs.
- Prefers an early line containing 2 to 4 alphabetic words in name-like format, title-casing uppercase text.
- Cleanly falls back to the title-cased filename if no valid textual name can be verified.

### Resulting Name Corrections
- `candidate_30.pdf`: Correctly identified as **`V Sree Raghu Vardhan`** (was `"SOFTWARE ENGINEER"`).
- `candidate_35.pdf`: Correctly skipped `"LinkedIn Github"` and `"Candidate Portfolio"`, falling back cleanly to **`Candidate 35`**.
- `candidate_10.pdf`: Title-cased from all-caps to **`Abhinav Mishra`**.

---

## 4. Top Candidates Comparison: Heuristic vs. Full LLM Evaluation

| Candidate Name | Run 1 Score (Heuristic Fallback) | Run 2 Score (Full LLM Evaluation) | Score Delta | Primary Driver of Shift |
|---|---|---|---|---|
| **Abhinav Mishra** | 71 | **96** | +25 | Full LLM recognized authentic Agentic RAG workflows, LangGraph routing, and FastAPI backend depth beyond simple keyword counting. |
| **Yash Maini** | 72 | **95** | +23 | High evaluation of dual IEEE first-author publications and custom RAG model benchmarking. |
| **Jyandeep Baishya** | 70 | **93** | +23 | Evaluated complex multi-agent event workflows and rigorous production backend microservices. |
| **Sumaiya Sultana Shaik** | 68 | **93** | +25 | Deep production FastAPI and enterprise RAG architecture evaluated accurately. |
| **Candidate 35** | 67 | **93** | +26 | Real-time WebSocket and production-grade RAG pipelines rewarded. |
| **V Sree Raghu Vardhan** | 68 | **90** | +22 | Rigorous backend engineering rewarded over superficial keyword density. |

---

## 5. Summary & Operational State

The pipeline achieved **100% LLM structured scoring coverage across all 30 eligible candidates**, eliminating heuristic fallbacks entirely through client-side rate regulation and model fallback tiers while protecting determinism through cached artifacts.
