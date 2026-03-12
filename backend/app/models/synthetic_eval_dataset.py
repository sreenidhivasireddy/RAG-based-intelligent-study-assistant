from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.sql import func

from app.database import Base


class SyntheticEvalDataset(Base):
    __tablename__ = "synthetic_eval_dataset"

    id = Column(String(36), primary_key=True, comment="UUID primary key")
    document_id = Column(
        String(32),
        ForeignKey("file_upload.file_md5"),
        nullable=False,
        index=True,
        comment="Document identifier (file_md5)",
    )
    chunk_id = Column(String(64), nullable=False, index=True, comment="Chunk identifier used for QA generation")
    question = Column(Text, nullable=False, comment="Synthetic question")
    answer = Column(Text, nullable=False, comment="Ground truth answer")
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="Created at")
    used_in_eval = Column(Boolean, nullable=False, default=False, server_default="0", comment="Marked after eval use")
    pipeline_version = Column(String(64), nullable=True, comment="Generation pipeline version")
