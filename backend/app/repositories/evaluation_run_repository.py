from typing import List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.evaluation_run import EvaluationRun


def get_next_run_label(db: Session, dataset_source: str) -> str:
    count = db.query(EvaluationRun).filter(EvaluationRun.dataset_source == dataset_source).count()
    return f"Run {count + 1}"


def create_evaluation_run(
    db: Session,
    mode: str,
    dataset_source: str,
    avg_groundedness: float,
    avg_relevance: float,
    avg_overall: float,
    avg_similarity: Optional[float],
    total_questions: int,
    succeeded: int,
    failed: int,
) -> EvaluationRun:
    run_label = get_next_run_label(db, dataset_source=dataset_source)
    run = EvaluationRun(
        id=str(uuid4()),
        run_label=run_label,
        mode=mode,
        dataset_source=dataset_source,
        avg_groundedness=avg_groundedness,
        avg_relevance=avg_relevance,
        avg_overall=avg_overall,
        avg_similarity=avg_similarity,
        total_questions=total_questions,
        succeeded=succeeded,
        failed=failed,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def list_evaluation_runs(
    db: Session,
    dataset_source: str | None = None,
    limit: int = 20,
) -> List[EvaluationRun]:
    query = db.query(EvaluationRun)
    if dataset_source:
        query = query.filter(EvaluationRun.dataset_source == dataset_source)
    return query.order_by(EvaluationRun.created_at.desc()).limit(limit).all()
