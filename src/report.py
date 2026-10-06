"""Output generation: JSON, CSV exporters, and rich terminal formatting."""

import csv
import json
import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import DEFAULT_CONFIG
from src.models import ScreeningReport

logger = logging.getLogger(__name__)


def export_json(
    report: ScreeningReport,
    output_path: Path | str,
    include_email: Optional[bool] = None,
) -> Path:
    """Export complete screening report to structured JSON."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    inc_email = (
        include_email
        if include_email is not None
        else DEFAULT_CONFIG.include_email_in_output
    )

    data = report.model_dump()

    # Filter out email if flag is False
    if not inc_email:
        for c in data.get("ranked_candidates", []):
            c.pop("email", None)
        for c in data.get("rejected_candidates", []):
            c.pop("email", None)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return out_file


def export_csv(
    report: ScreeningReport,
    output_path: Path | str,
    include_email: Optional[bool] = None,
) -> Path:
    """Export ranked candidates to CSV."""
    json_path = Path(output_path)
    csv_path = json_path.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    inc_email = (
        include_email
        if include_email is not None
        else DEFAULT_CONFIG.include_email_in_output
    )

    headers = [
        "rank",
        "candidate_name",
        "total_score",
        "ai_project_depth",
        "python_backend",
        "cloud_fullstack",
        "github",
        "engineering_depth",
        "thin_wrapper_penalty",
        "scoring_method",
        "github_status",
        "matched_skills",
        "project_summary",
        "source_file",
    ]
    if inc_email:
        headers.insert(2, "email")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for cand in report.ranked_candidates:
            row = {
                "rank": cand.rank,
                "candidate_name": cand.candidate_name,
                "total_score": cand.total_score,
                "ai_project_depth": cand.score_breakdown.ai_project_depth,
                "python_backend": cand.score_breakdown.python_backend,
                "cloud_fullstack": cand.score_breakdown.cloud_fullstack,
                "github": cand.score_breakdown.github,
                "engineering_depth": cand.score_breakdown.engineering_depth,
                "thin_wrapper_penalty": cand.thin_wrapper_penalty,
                "scoring_method": cand.scoring_method,
                "github_status": cand.github_status,
                "matched_skills": "; ".join(cand.matched_skills),
                "project_summary": cand.project_summary,
                "source_file": cand.source_file,
            }
            if inc_email:
                row["email"] = cand.email or ""
            writer.writerow(row)

    return csv_path


def print_terminal_summary(report: ScreeningReport, top_n: int = 10) -> None:
    """Display clean terminal table for top candidates and batch summary."""
    console = Console()

    # Top candidates table
    table = Table(title=f"Top {top_n} Ranked Candidates", header_style="bold cyan")
    table.add_column("Rank", justify="center", style="bold green", width=6)
    table.add_column("Name", style="bold white", min_width=20)
    table.add_column("Score", justify="right", style="bold yellow", width=7)
    table.add_column("AI Depth", justify="right", width=9)
    table.add_column("Python", justify="right", width=8)
    table.add_column("Cloud/FS", justify="right", width=9)
    table.add_column("GitHub", justify="right", width=8)
    table.add_column("Method", justify="center", width=12)

    for cand in report.ranked_candidates[:top_n]:
        bd = cand.score_breakdown
        table.add_row(
            str(cand.rank or "-"),
            cand.candidate_name,
            f"{cand.total_score}/100",
            f"{bd.ai_project_depth}/40",
            f"{bd.python_backend}/30",
            f"{bd.cloud_fullstack}/15",
            f"{bd.github}/10",
            cand.scoring_method,
        )

    console.print(table)

    # Batch summary panel
    bs = report.batch_summary
    summary_text = (
        f"[bold]Total Files Scanned:[/bold] {bs.total_files}  |  "
        f"[bold green]Parsed:[/bold green] {bs.successfully_parsed}  |  "
        f"[bold red]Unreadable:[/bold red] {bs.failed_unreadable}\n"
        f"[bold cyan]Eligible Candidates:[/bold cyan] {bs.eligible}  |  "
        f"[bold magenta]Rejected Candidates:[/bold magenta] {bs.rejected}  |  "
        f"[bold yellow]Duplicates:[/bold yellow] {bs.duplicates}\n"
        f"[bold]LLM Fallbacks:[/bold] {bs.llm_fallbacks}  |  "
        f"[bold]GitHub Failures:[/bold] {bs.github_failures}  |  "
        f"[bold]Run Time:[/bold] {bs.run_seconds}s"
    )
    console.print(Panel(summary_text, title="Batch Execution Summary", border_style="blue"))
