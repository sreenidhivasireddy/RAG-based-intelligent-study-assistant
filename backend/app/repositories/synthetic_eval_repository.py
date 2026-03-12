from collections import Counter
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.file_upload import FileUpload
from app.models.synthetic_eval_dataset import SyntheticEvalDataset


def create_many_synthetic_eval_rows(
    db: Session,
    rows: List[Dict[str, str]],
    pipeline_version: Optional[str] = None,
) -> List[SyntheticEvalDataset]:
    items: List[SyntheticEvalDataset] = []
    for row in rows:
        item = SyntheticEvalDataset(
            id=str(uuid4()),
            document_id=str(row["document_id"]),
            chunk_id=str(row["chunk_id"]),
            question=str(row["question"]),
            answer=str(row["answer"]),
            used_in_eval=False,
            pipeline_version=pipeline_version,
        )
        items.append(item)
    if not items:
        return []
    db.add_all(items)
    db.commit()
    return items


def list_synthetic_eval_rows(
    db: Session,
    document_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[SyntheticEvalDataset]:
    query = db.query(SyntheticEvalDataset)
    if document_id:
        query = query.filter(SyntheticEvalDataset.document_id == document_id)
    return (
        query.order_by(SyntheticEvalDataset.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_synthetic_eval_rows(db: Session, document_id: Optional[str] = None) -> int:
    query = db.query(SyntheticEvalDataset)
    if document_id:
        query = query.filter(SyntheticEvalDataset.document_id == document_id)
    return query.count()


def get_synthetic_eval_row(db: Session, row_id: str) -> Optional[SyntheticEvalDataset]:
    return db.query(SyntheticEvalDataset).filter(SyntheticEvalDataset.id == row_id).first()


def delete_synthetic_eval_row(db: Session, row_id: str) -> bool:
    row = get_synthetic_eval_row(db, row_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def delete_synthetic_eval_rows_by_document_id(db: Session, document_id: str) -> int:
    rows = db.query(SyntheticEvalDataset).filter(SyntheticEvalDataset.document_id == document_id).all()
    deleted = len(rows)
    for row in rows:
        db.delete(row)
    db.commit()
    return deleted


def fetch_synthetic_eval_rows_for_evaluation(
    db: Session,
    limit: int = 200,
    only_unused: bool = True,
) -> List[SyntheticEvalDataset]:
    query = db.query(SyntheticEvalDataset).join(
        FileUpload,
        SyntheticEvalDataset.document_id == FileUpload.file_md5,
    )
    if only_unused:
        query = query.filter(SyntheticEvalDataset.used_in_eval.is_(False))
    return query.order_by(SyntheticEvalDataset.created_at.asc()).limit(limit).all()


def mark_synthetic_eval_rows_used(db: Session, ids: List[str]) -> int:
    if not ids:
        return 0
    rows = db.query(SyntheticEvalDataset).filter(SyntheticEvalDataset.id.in_(ids)).all()
    for row in rows:
        row.used_in_eval = True
    db.commit()
    return len(rows)


def synthetic_eval_stats(db: Session) -> Dict[str, object]:
    rows = db.query(SyntheticEvalDataset).all()
    total_questions = len(rows)
    per_document = Counter(row.document_id for row in rows)
    used_count = sum(1 for row in rows if row.used_in_eval)
    unused_count = total_questions - used_count
    document_count = len(per_document)
    avg_questions_per_document = round(total_questions / document_count, 2) if document_count else 0.0
    return {
        "total_questions": total_questions,
        "questions_per_document": dict(per_document),
        "coverage": {
            "documents_with_questions": document_count,
            "used_in_eval": used_count,
            "unused": unused_count,
            "avg_questions_per_document": avg_questions_per_document,
        },
    }
