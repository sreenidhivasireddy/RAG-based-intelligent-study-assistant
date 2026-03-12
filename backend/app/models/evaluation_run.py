from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id = Column(String(36), primary_key=True, comment="UUID primary key")
    run_label = Column(String(32), nullable=False, index=True, comment="Dataset-specific run label")
    mode = Column(String(16), nullable=False, index=True, comment="Evaluation mode")
    dataset_source = Column(String(16), nullable=False, index=True, comment="Dataset source used")
    avg_groundedness = Column(Float, nullable=False, default=0.0)
    avg_relevance = Column(Float, nullable=False, default=0.0)
    avg_overall = Column(Float, nullable=False, default=0.0)
    avg_similarity = Column(Float, nullable=True)
    total_questions = Column(Integer, nullable=False, default=0)
    succeeded = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), index=True)
