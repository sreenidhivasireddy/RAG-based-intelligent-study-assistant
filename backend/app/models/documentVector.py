"""
DocumentVector ORM model for storing metadata of parsed chunk text and corresponding vector data.
"""

from sqlalchemy import Column, String, Integer, BigInteger, Text
from app.database import Base

class DocumentVector(Base):
    """Document vector metadata table."""
    __tablename__ = "document_vectors"

    vector_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Unique ID of the vector record")
    file_md5 = Column(String(32), nullable=False, name="file_md5", comment="Associated file MD5 hash")
    chunk_id = Column(Integer, nullable=False, name="chunk_id", comment="Text chunk sequence number")
    text_content = Column(Text, nullable=False, name="text_content", comment="Extracted text content")
    model_version = Column(String(32), nullable=False, name="model_version", comment="Version of the embedding model")
