from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.database import Base


class FixedEvalDataset(Base):
    __tablename__ = "fixed_eval_dataset"

    id = Column(String(36), primary_key=True, comment="UUID primary key")
    question = Column(Text, nullable=False, comment="Fixed evaluation question")
    expected_answer = Column(Text, nullable=False, comment="Ground truth answer")
    topic = Column(String(128), nullable=False, index=True, comment="Topic label")
    difficulty = Column(String(16), nullable=False, index=True, comment="Difficulty: easy|medium|hard")
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="Created at")
