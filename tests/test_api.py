from pathlib import Path
from fastapi.testclient import TestClient
from src.api import app

client = TestClient(app)


def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_api_screen_and_results(tmp_path: Path):
    test_resume_dir = tmp_path / "resumes"
    test_resume_dir.mkdir()

    r1 = test_resume_dir / "alex.txt"
    r1.write_text(
        """Alex Rivers
alex@rivers.com
https://github.com/alexrivers
Skills: Python, FastAPI, LangGraph
Experience: Built LangGraph multi-agent systems with FastAPI.
""",
        encoding="utf-8",
    )

    out_file = tmp_path / "output" / "api_results.json"

    # POST /screen
    payload = {
        "input_path": str(test_resume_dir),
        "no_llm": True,
        "max_workers": 2,
        "output_path": str(out_file),
    }
    response = client.post("/screen", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["batch_summary"]["total_files"] == 1
    assert data["batch_summary"]["eligible"] == 1
    assert len(data["ranked_candidates"]) == 1

    # GET /results
    res_get = client.get("/results", params={"output_path": str(out_file)})
    assert res_get.status_code == 200
    get_data = res_get.json()
    assert get_data["batch_summary"]["total_files"] == 1
    assert get_data["ranked_candidates"][0]["candidate_name"] == "Alex Rivers"


def test_api_missing_input_path():
    response = client.post("/screen", json={"input_path": "./nonexistent_folder_xyz"})
    assert response.status_code == 400


def test_api_missing_results():
    response = client.get("/results", params={"output_path": "./nonexistent_file.json"})
    assert response.status_code == 404
