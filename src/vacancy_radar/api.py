"""FastAPI app: /analyze /similar /ingest/vacancy /healthz.

M1 scaffold — only /healthz is live initially. /similar is implemented (M3); /analyze and
/ingest/vacancy are still wired but not implemented (M2/M4); they return 501 rather than 404
so the API surface is stable from day one for anything that starts integrating against it early.
"""

from fastapi import Depends, FastAPI, HTTPException

from vacancy_radar.models import Report, SimilarVacancy
from vacancy_radar.retriever import Retriever

app = FastAPI(title="Vacancy Radar", version="0.1.0")


def get_retriever() -> Retriever:
    return Retriever()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=Report)
def analyze(jd_text: str) -> Report:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M4 in the roadmap")


@app.post("/similar", response_model=list[SimilarVacancy])
def similar(
    jd_text: str, retriever: Retriever = Depends(get_retriever)
) -> list[SimilarVacancy]:
    if not jd_text.strip():
        raise HTTPException(status_code=422, detail="jd_text must not be empty")
    return retriever.query_similar_vacancies(jd_text)


@app.post("/ingest/vacancy")
def ingest_vacancy(vacancy_folder: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Not implemented yet — see M2 in the roadmap")
