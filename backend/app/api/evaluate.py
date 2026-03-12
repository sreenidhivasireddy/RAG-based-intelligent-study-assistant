from fastapi import APIRouter, HTTPException

from app.database import SessionLocal
from app.repositories.evaluation_run_repository import list_evaluation_runs
from app.schemas.evaluation import AutomatedEvalResponse, DatasetSource, EvaluationRegressionPoint, EvaluationRunRequest
from app.services.automated_evaluation import run_automated_evaluation
from app.utils.logging import get_logger


router = APIRouter(prefix="/evaluate", tags=["evaluate"])
logger = get_logger(__name__)


@router.post("/run", response_model=AutomatedEvalResponse)
async def run_evaluation_pipeline(
    request: EvaluationRunRequest | None = None,
):
    try:
        payload = request or EvaluationRunRequest()
        return run_automated_evaluation(
            dataset_source=payload.dataset_source or "synthetic",
        )
    except Exception as e:
        logger.error("Automated evaluation run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Automated evaluation run failed: {str(e)}")


@router.get("/history", response_model=list[EvaluationRegressionPoint])
async def get_evaluation_history(
    dataset_source: DatasetSource = "fixed",
    limit: int = 20,
):
    db = SessionLocal()
    try:
        runs = list_evaluation_runs(db, dataset_source=dataset_source, limit=limit)
        return [
            EvaluationRegressionPoint(
                run_id=run.id,
                run_label=run.run_label,
                timestamp=run.created_at,
                dataset_source=run.dataset_source,
                avg_groundedness=run.avg_groundedness,
                avg_relevance=run.avg_relevance,
                avg_overall=run.avg_overall,
                avg_similarity=run.avg_similarity,
            )
            for run in reversed(runs)
        ]
    finally:
        db.close()
