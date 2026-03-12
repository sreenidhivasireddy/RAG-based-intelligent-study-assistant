from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.repositories.synthetic_eval_repository import (
    count_synthetic_eval_rows,
    delete_synthetic_eval_row,
    delete_synthetic_eval_rows_by_document_id,
    list_synthetic_eval_rows,
    synthetic_eval_stats,
)
from app.schemas.evaluation import (
    SyntheticEvalDatasetItem,
    SyntheticEvalDatasetListResponse,
    SyntheticEvalRegenerateResponse,
    SyntheticEvalStatsResponse,
)
from app.services.synthetic_eval_generation import generate_synthetic_eval_for_document
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/eval/synthetic-dataset", tags=["synthetic-eval-dataset"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=SyntheticEvalDatasetListResponse)
def get_synthetic_dataset(
    document_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    rows = list_synthetic_eval_rows(db, document_id=document_id, limit=limit, offset=offset)
    total = count_synthetic_eval_rows(db, document_id=document_id)
    return SyntheticEvalDatasetListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            SyntheticEvalDatasetItem(
                id=row.id,
                document_id=row.document_id,
                chunk_id=row.chunk_id,
                question=row.question,
                answer=row.answer,
                created_at=row.created_at,
                used_in_eval=row.used_in_eval,
                pipeline_version=row.pipeline_version,
            )
            for row in rows
        ],
    )


@router.get("/stats", response_model=SyntheticEvalStatsResponse)
def get_synthetic_dataset_stats(db: Session = Depends(get_db)):
    stats = synthetic_eval_stats(db)
    return SyntheticEvalStatsResponse(**stats)


@router.delete("/{id}")
def delete_synthetic_dataset_row(id: str, db: Session = Depends(get_db)):
    deleted = delete_synthetic_eval_row(db, row_id=id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Synthetic eval row not found: {id}")
    return {"deleted": True, "id": id}


@router.post("/regenerate/{document_id}", response_model=SyntheticEvalRegenerateResponse)
def regenerate_synthetic_dataset(document_id: str, db: Session = Depends(get_db)):
    deleted_old_rows = delete_synthetic_eval_rows_by_document_id(db, document_id=document_id)
    logger.info(
        "Synthetic eval regenerate requested document_id=%s deleted_old_rows=%d",
        document_id,
        deleted_old_rows,
    )
    generated_rows = generate_synthetic_eval_for_document(
        document_id=document_id,
        pipeline_version="synthetic-v1",
        replace_existing=False,
    )
    return SyntheticEvalRegenerateResponse(
        document_id=document_id,
        deleted_old_rows=deleted_old_rows,
        generated_rows=generated_rows,
    )
