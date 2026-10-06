"""Orchestration pipeline wiring ingestion, extraction, eligibility, scoring, and enrichment."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import time
from typing import Optional

from src.config import DEFAULT_CONFIG
from src.extraction import extract_candidate_info
from src.eligibility import evaluate_eligibility
from src.github_enrichment import enrich_github_profiles
from src.ingestion import ingest_resumes
from src.llm import assess_candidate
from src.models import (
    BatchSummary,
    ExtractedInfo,
    ParsedResume,
    RankedCandidate,
    RejectedCandidate,
    ScreeningReport,
    ScoringMethod,
)
from src.scoring import assemble_candidate_score, rank_candidates

logger = logging.getLogger(__name__)


def run_screening_pipeline(
    input_path: Path | str,
    no_llm: bool = False,
    max_workers: Optional[int] = None,
    cache_dir: Optional[Path] = None,
) -> ScreeningReport:
    """Execute complete screening pipeline over input files or directory."""
    start_time = time.perf_counter()
    workers = max_workers or DEFAULT_CONFIG.max_workers
    cache = cache_dir or DEFAULT_CONFIG.cache_dir

    parsed_resumes, failures = ingest_resumes(input_path)
    total_files = len(parsed_resumes) + len(failures)
    successfully_parsed = len(parsed_resumes)
    failed_unreadable = len(failures)

    ranked_candidates: list[RankedCandidate] = []
    rejected_candidates: list[RejectedCandidate] = []
    duplicates_count = 0
    llm_fallbacks = 0

    seen_emails: dict[str, str] = {}
    eligible_queue: list[tuple[ParsedResume, ExtractedInfo]] = []

    # Process parsed resumes
    for resume in parsed_resumes:
        if resume.is_duplicate:
            duplicates_count += 1
            rejected_candidates.append(
                RejectedCandidate(
                    candidate_name=Path(resume.source_file).stem,
                    eligible=False,
                    rejection_reasons=[f"Duplicate file of {resume.duplicate_of}"],
                    matched_skills=[],
                    needs_review=False,
                    source_file=resume.source_file,
                )
            )
            continue

        try:
            extracted = extract_candidate_info(
                resume.raw_text, resume.source_file, resume.links
            )
            # Check duplicate email
            if extracted.email:
                if extracted.email in seen_emails:
                    duplicates_count += 1
                    orig_file = seen_emails[extracted.email]
                    rejected_candidates.append(
                        RejectedCandidate(
                            candidate_name=extracted.candidate_name,
                            email=extracted.email,
                            eligible=False,
                            rejection_reasons=[
                                f"Duplicate email '{extracted.email}' already seen in {orig_file}"
                            ],
                            matched_skills=extracted.matched_skills,
                            needs_review=True,
                            source_file=resume.source_file,
                        )
                    )
                    continue
                seen_emails[extracted.email] = resume.source_file

            # Evaluate hard eligibility
            eligibility = evaluate_eligibility(
                resume.raw_text, extracted.matched_skills
            )
            if not eligibility.eligible:
                rejected_candidates.append(
                    RejectedCandidate(
                        candidate_name=extracted.candidate_name,
                        email=extracted.email,
                        eligible=False,
                        rejection_reasons=eligibility.rejection_reasons,
                        matched_skills=extracted.matched_skills,
                        needs_review=eligibility.needs_review,
                        source_file=resume.source_file,
                    )
                )
            else:
                eligible_queue.append((resume, extracted))

        except Exception as exc:
            logger.error(f"Error processing {resume.source_file}: {exc}")
            rejected_candidates.append(
                RejectedCandidate(
                    candidate_name=Path(resume.source_file).stem,
                    eligible=False,
                    rejection_reasons=[f"Processing error: {str(exc)}"],
                    matched_skills=[],
                    needs_review=True,
                    source_file=resume.source_file,
                )
            )

    # Enrich GitHub profiles concurrently
    github_handles = [item[1].github_username for item in eligible_queue]
    github_map = enrich_github_profiles(
        github_handles, max_workers=workers, cache_dir=cache
    )

    # Assess eligible candidates with bounded concurrency
    def _assess_worker(item: tuple[ParsedResume, ExtractedInfo]):
        r, ext = item
        gh_data = github_map.get(ext.github_username) or github_map.get(None)
        try:
            assessment = assess_candidate(
                r.raw_text, ext, no_llm=no_llm, cache_dir=cache
            )
        except Exception as exc:
            logger.warning(f"Assessment worker failed for {ext.candidate_name}: {exc}")
            assessment = None

        scored = assemble_candidate_score(
            r.raw_text, ext, gh_data, assessment, r.source_file
        )
        return scored

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_assess_worker, item): item for item in eligible_queue}
        for fut in as_completed(futures):
            try:
                candidate = fut.result()
                if candidate.scoring_method == ScoringMethod.HEURISTIC_FALLBACK.value:
                    llm_fallbacks += 1
                ranked_candidates.append(candidate)
            except Exception as exc:
                item = futures[fut]
                logger.error(f"Candidate scoring crash on {item[1].candidate_name}: {exc}")

    # Rank eligible candidates
    ranked_candidates = rank_candidates(ranked_candidates)

    github_failures = sum(
        1 for c in ranked_candidates if c.github_status in ("error", "rate_limited", "not_found")
    )
    elapsed = round(time.perf_counter() - start_time, 2)

    summary = BatchSummary(
        total_files=total_files,
        successfully_parsed=successfully_parsed,
        eligible=len(ranked_candidates),
        rejected=len(rejected_candidates),
        failed_unreadable=failed_unreadable,
        duplicates=duplicates_count,
        llm_fallbacks=llm_fallbacks,
        github_failures=github_failures,
        run_seconds=elapsed,
    )

    return ScreeningReport(
        batch_summary=summary,
        ranked_candidates=ranked_candidates,
        rejected_candidates=rejected_candidates,
        failed_files=failures,
    )
