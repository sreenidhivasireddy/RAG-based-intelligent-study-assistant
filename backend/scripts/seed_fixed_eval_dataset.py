from pathlib import Path

from app.database import SessionLocal, ensure_tables
from app.repositories.fixed_eval_repository import seed_fixed_eval_questions_from_file


def main() -> None:
    ensure_tables()
    seed_path = Path(__file__).resolve().parents[1] / "data" / "fixed_eval_dataset.json"
    db = SessionLocal()
    try:
        count = seed_fixed_eval_questions_from_file(db, seed_path)
        print(f"Seeded fixed evaluation dataset rows={count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
