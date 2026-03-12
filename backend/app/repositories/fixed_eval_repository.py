import json
from pathlib import Path
from typing import List
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.fixed_eval_dataset import FixedEvalDataset


def list_fixed_eval_questions(db: Session, limit: int | None = None) -> List[FixedEvalDataset]:
    query = db.query(FixedEvalDataset).order_by(FixedEvalDataset.created_at.asc())
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def count_fixed_eval_questions(db: Session) -> int:
    return db.query(FixedEvalDataset).count()


def replace_fixed_eval_questions(db: Session, rows: List[dict]) -> int:
    db.query(FixedEvalDataset).delete()
    items: List[FixedEvalDataset] = []
    for row in rows:
        items.append(
            FixedEvalDataset(
                id=str(row.get("id") or uuid4()),
                question=str(row["question"]).strip(),
                expected_answer=str(row["expected_answer"]).strip(),
                topic=str(row["topic"]).strip(),
                difficulty=str(row["difficulty"]).strip(),
            )
        )
    if items:
        db.add_all(items)
    db.commit()
    return len(items)


def seed_fixed_eval_questions_from_file(db: Session, seed_path: Path) -> int:
    raw = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Fixed eval seed file must contain a JSON array.")
    return replace_fixed_eval_questions(db, raw)
