"""AI Resume Screening & Ranking CLI."""

import argparse
import logging
import sys
from pathlib import Path

from src.config import DEFAULT_CONFIG
from src.pipeline import run_screening_pipeline
from src.report import export_json, export_csv, print_terminal_summary


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Resume Screening & Ranking CLI - Production-minded backend evaluation."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default="./resumes",
        help="Input folder or file containing resumes (PDF/DOCX/TXT)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="./output/results.json",
        help="Target output path for results JSON file (CSV will be co-located)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Force deterministic heuristic scoring instead of calling LLM provider",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=DEFAULT_CONFIG.max_workers,
        help="Maximum concurrent worker threads for LLM and GitHub calls",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top candidates to display in terminal summary",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input path '{input_path}' does not exist.", file=sys.stderr)
        return 1

    report = run_screening_pipeline(
        input_path=input_path,
        no_llm=args.no_llm,
        max_workers=args.workers,
    )

    json_file = export_json(report, args.output)
    csv_file = export_csv(report, args.output)

    print_terminal_summary(report, top_n=args.top)
    print(f"\n[Artifacts Saved]\n- JSON: {json_file}\n- CSV:  {csv_file}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
