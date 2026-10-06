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
- `candidate_28.pdf`: Extracted cleanly as **`Sumaiya Sultana Shaik`**.

---

## 4. Before vs. After: Scoring & Ranking Comparison

Below is the comparison of the Top 10 candidates between **Run 1** (predominantly heuristic fallback) and **Run 2** (100% LLM structured assessment):

| Rank | Run 1 (Heuristic Fallback Dominant) | Score | Method | Run 2 (100% LLM Evaluated) | Score | Method | Key Architectural Insight / Rank Shift |
|:---:|:---|:---:|:---:|:---|:---:|:---:|:---|
| **1** | Abhinav Mishra | 96 | `llm` | **Abhinav Mishra** | **96** | `llm` | Retained #1; exceptional LangGraph multi-agent orchestration, tool calling, and high-throughput async FastAPI. |
| **2** | *LinkedIn Github* (cand 35) | 95 | `fallback` | **Yash Maini** | **95** | `llm` | **Climbed from #5 to #2**. LLM recognized deep hybrid RAG with reranking & production FastAPI over mere keyword counts. |
| **3** | *SOFTWARE ENGINEER* (cand 30) | 95 | `fallback` | **Jyandeep Baishya** | **93** | `llm` | Retained top-tier standing with verified LangChain agent evaluation and Dockerized deployment. |
| **4** | Jyandeep Baishya | 93 | `llm` | **Sumaiya Sultana Shaik** | **93** | `llm` | **Rose from #6 to #4**. AI Depth evaluated at 37/40 with verified vector database retrieval and Celery queues. |
| **5** | Yash Maini | 93 | `fallback` | **Candidate 35** | **93** | `llm` | Name corrected; deep agentic tool integration scored 38/40 with 15/15 cloud infrastructure. |
| **6** | candidate_28 | 91 | `fallback` | **V Sree Raghu Vardhan** | **90** | `llm` | Name corrected from job title; verified PostgreSQL, Redis, and LangChain project experience. |
| **7** | candidate_22 | 91 | `fallback` | **Arjun Kumar** | **88** | `llm` | **Rose from #10 to #7**. Rigorous engineering metrics and LLM evaluation pipeline rewarded by model. |
| **8** | candidate_41 | 90 | `fallback` | **Prajwal A S** | **87** | `llm` | Verified FastAPI backend with Docker and Pinecone vector store. |
| **9** | candidate_33 | 89 | `fallback` | **Vaibhav Wakde** | **86** | `llm` | Solid Python backend with AWS deployment and conversational RAG. |
| **10** | Arjun Kumar | 88 | `llm` | **Hari Shanker Sharma** | **86** | `llm` | Fullstack AI engineer with React, FastAPI, and ChromaDB embeddings. |

### Observations on Ranking Shifts
1. **Separation of Real Depth vs Keyword Stuffing**:
   Heuristic fallback relied on keyword presence in project sections, clustering scores at 95. The LLM differentiated between superficial API calls and authentic system engineering (tool definitions, state machines, retrieval reranking), creating a much more granular and justifiable distribution.
2. **Elimination of Title/Header Hallucinations**:
   Job titles and social media icons no longer appear as candidate names in the leaderboard.
3. **Deterministic Guard Enforcement**:
   Every LLM evaluation was checked against post-guards A–E (quote verification, clamping, and low-AI depth caps), ensuring that no candidate bypassed deterministic constraints.
