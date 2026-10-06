"""FastAPI web wrapper exposing screening endpoints."""

from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.config import DEFAULT_CONFIG
from src.pipeline import run_screening_pipeline
from src.report import export_json, export_csv
from src.models import ScreeningReport

app = FastAPI(
    title="AI Resume Screening & Ranking API",
    description="Production-minded backend service for resume eligibility filtering and ranking.",
    version="1.0.0",
)


class ScreenRequest(BaseModel):
    input_path: str = Field(
        default="./resumes", description="Directory or file path containing resumes"
    )
    no_llm: bool = Field(
        default=False, description="Force deterministic heuristic fallback mode"
    )
    max_workers: int = Field(
        default=4, description="Maximum concurrent worker threads"
    )
    output_path: str = Field(
        default="./output/results.json", description="Target output path for results JSON"
    )


@app.get("/health")
def health_check():
    """Service health check."""
    return {"status": "healthy", "service": "resume-ranker"}


@app.post("/screen", response_model=ScreeningReport)
def screen_resumes(req: ScreenRequest):
    """Execute resume screening and ranking pipeline on specified input path."""
    target = Path(req.input_path)
    if not target.exists():
        raise HTTPException(status_code=400, detail=f"Input path '{req.input_path}' not found")

    try:
        report = run_screening_pipeline(
            input_path=target,
            no_llm=req.no_llm,
            max_workers=req.max_workers,
        )
        export_json(report, req.output_path)
        export_csv(report, req.output_path)
        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Screening pipeline error: {exc}")


@app.get("/results", response_model=ScreeningReport)
def get_results(output_path: str = Query("./output/results.json", description="Path to results JSON")):
    """Retrieve existing screening results from disk."""
    path = Path(output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No existing results found. Run POST /screen first.")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        return ScreeningReport.model_validate_json(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read results: {exc}")
