# Batch Run Notes: AI Resume Screening & Ranking (Final Notes)

This document contains the final operational notes, verified execution statistics, candidate ranking tables, and architectural learnings from evaluating the 50 candidate resumes in `./resumes`.

---

## 1. Run History

| Run | Reference Document | Description & Key Results |
|---|---|---|
| **Run 1** | [run1.md](run1.md) | Baseline run with initial parser and concurrency. 24 of 30 eligible candidates fell back to deterministic heuristic scoring due to Google Gemini Free Tier 5 RPM rate limits. |
| **Run 2** | [run2.md](run2.md) | Added thread-safe client-side rate limiter (`LLM_RPM=5`), retry delay parser, and model fallback tier (`gemini-3.5-flash-lite`). Achieved 30 of 30 eligible scored by LLM. |
| **Final Run** | *Current Run* (`run_notes.md`) | Robust layout-based name extraction with multi-span merging, font size scoring, and contact overlap. Corrected `candidate_21` ("Manoj Kumar K R"), `candidate_35` ("Prathamesh Patil"), and `candidate_20` ("Priya R"). 100% cache hit replay with identical scores. |

---

## 2. Final Batch Statistics

Computed directly from `output/results.json`:

- **Total Resumes Scanned**: 50
- **Successfully Parsed**: 50 (100%)
- **Unreadable / Corrupt**: 0
- **Duplicate Files**: 0
- **Eligible Candidates**: 30 (60.0%)
- **Rejected Candidates**: 20 (40.0%)
- **Borderline / `needs_review` Count**: 16 (out of 20 rejected applicants)
- **Scoring Method Counts**:
  - `llm`: 30 (100.0%)
  - `heuristic_fallback`: 0 (0.0%)
- **GitHub Status Counts**:
  - `ok`: 27
  - `not_provided`: 2
  - `not_found`: 1
  - `error`: 0
- **Pipeline Execution Time**: 1.2s (with all 30 evaluations and GitHub profiles retrieved from disk cache)

---

## 3. Name Extraction: Diagnosis, Fix, and Audit

### Diagnosis of Name Failures
1. **`candidate_21.pdf`** was previously extracted as `"Higher Secondary Science- PCMB"`:
   - *Cause*: The PDF's internal text stream placed education and summary blocks before the header. Without font-size awareness or education filters, the first line satisfying length checks was selected, missing the actual name (`MANOJ KUMAR K R`, 18pt font at the top).
2. **`candidate_35.pdf`** was previously extracted as `"Candidate 35"`:
   - *Cause*: The candidate's name was split across two stacked lines—`"Prathamesh"` (23.9pt) and `"Patil"` (17.9pt). The strict word-count filter ($2 \le \text{words} \le 4$) rejected each line independently, exhausting text lines and triggering filename fallback.
3. **`candidate_20.pdf`** was previously extracted as `"Programming Language Python"`:
   - *Cause*: The candidate's name `"PRIYA R"` appeared in a separate block at 34pt font, while lower skill narrative text was picked by the sequential line scanner.

### The Fix
- **PDF Layout Extraction**: Preserves Page 1 text lines and spans with font size, $y$-position, and bounding box coordinates (`(text, font_size, y, x)`).
- **Candidate Merging**: Merges consecutive spans on the same line and multi-line name blocks in the top third of Page 1.
- **Hard Rejection Rules**: Rejects lines containing `@`, digits, URLs, $<2$ or $>5$ words, $<3.0$ average letters per word, or any of 48 section/education/job-title keywords (`education`, `secondary`, `science`, `pcmb`, `bachelor`, `b.tech`, `portfolio`, `engineer`, `developer`, etc.).
- **Signal-Weighted Scoring**: Scores candidate lines based on relative font size above page median ($+3.5\times$), top-of-page vertical position (up to $+20$), title case/ALL CAPS format ($+12$), and strong contact overlap ($+25$ per token matching email, GitHub, or LinkedIn slug).
- **Sequential Fallbacks**: (a) Email local part if splitting into 2–3 alphabetic tokens; (b) LinkedIn slug; (c) Title-cased filename.

### Final Audit Results
Across all 50 resumes in `./resumes`:
- **`name_source` Counts**:
  - `layout`: 50 (100%)
  - `text`: 0
  - `email`: 0
  - `linkedin`: 0
  - `filename`: 0
- **Flagged Names**: 0 (no keyword collisions, no $>4$ word names, zero filename fallbacks).
- **Unrecoverable Names**: 0 (all 50 resumes have recoverable text-layer names).

---

## 4. Top 10 Ranked Candidates

Extracted from the final `output/results.json`:

| Rank | Candidate Name | Name Source | Total Score | AI Depth (40) | Python Backend (30) | Cloud / FS (15) | GitHub (10) | Rigor (5) | Scoring Method |
|---|---|---|---|---|---|---|---|---|---|
| **1** | Abhinav Mishra | layout | **96** | 37 | 29 | 15 | 10 | 5 | llm |
| **2** | Yash Maini | layout | **95** | 39 | 29 | 15 | 7 | 5 | llm |
| **3** | Jyandeep Baishya | layout | **93** | 38 | 28 | 12 | 10 | 5 | llm |
| **4** | Sumaiya Sultana Shaik | layout | **93** | 37 | 29 | 14 | 8 | 5 | llm |
| **5** | Prathamesh Patil | layout | **93** | 38 | 29 | 15 | 6 | 5 | llm |
| **6** | V Sree Raghu Vardhan | layout | **90** | 38 | 28 | 13 | 6 | 5 | llm |
| **7** | Arjun Kumar | layout | **88** | 35 | 28 | 13 | 8 | 4 | llm |
| **8** | Prajwal A S | layout | **87** | 38 | 28 | 10 | 6 | 5 | llm |
| **9** | Vaibhav Wakde | layout | **86** | 38 | 28 | 8 | 8 | 4 | llm |
| **10** | Hari Shanker Sharma | layout | **86** | 35 | 28 | 12 | 6 | 5 | llm |

---

## 5. Known Limitations

1. **Temporal Blindness (Future Dates Flagging)**:
   The evaluation prompt did not supply the current execution date to the LLM. Consequently, the model flagged graduation dates and ongoing internships in 2025–2026 as suspicious "future dates" in the `concerns` field for approximately one-third of candidates, even though those dates are standard for graduating seniors and current roles.
2. **Dual-Model Contribution**:
   Because `gemini-2.5-flash` reached its 20 requests-per-day free tier quota mid-batch during Run 2, the rate limiter switched subsequent requests to `gemini-3.5-flash-lite`. While both models followed the identical Pydantic schema and strict JSON output constraints, minor calibration differences between the models contributed to the final score distribution.
3. **Absence of Labelled Ground Truth**:
   The screening criteria and weights reflect target engineering expectations, but have not been calibrated against human hiring manager accept/reject labels. Absolute cutoff thresholds should be reviewed against human recruiter preferences.
