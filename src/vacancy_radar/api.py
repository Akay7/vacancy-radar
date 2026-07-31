"""FastAPI app: /analyze /similar /ingest/vacancy /healthz.

M1 scaffold — only /healthz is live. The others are wired but not implemented
yet (M2-M4); they return 501 rather than 404 so the API surface is stable from
day one for anything that starts integrating against it early.
"""

from fastapi import FastAPI, HTTPException

from vacancy_radar.models import Report

app = FastAPI(title="Vacancy Radar", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=Report)
def analyze(jd_text: str) -> Report:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M4 in the roadmap")


@app.post("/similar")
def similar(jd_text: str) -> list[dict]:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M3 in the roadmap")


@app.post("/ingest/vacancy")
def ingest_vacancy(vacancy_folder: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M2 in the roadmap")
