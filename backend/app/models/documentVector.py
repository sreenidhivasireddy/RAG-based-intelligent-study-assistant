"""
DocumentVector ORM model for storing metadata of parsed chunk text and corresponding vector data.
"""

from sqlalchemy import Column, String, Integer, BigInteger
from app.database import Base

class DocumentVector(Base):
    """Document vector metadata table."""
    __tablename__ = "document_vectors"

    vector_id = Column(BigInteger, primary_key=True, autoincrement = True, comment = "Unique ID of the vector record")
    fileMd5 = Column(String(32), nullable = False, comment = "Associated file MD5 hash")
    chunkId = Column(Integer, nullable = False, comment = "Text chunk sequence number")
    textContent = Column(Text, nullable = False, comment = "Extracted text content")
    modelVersion = Column(String(32), nullable = False, comment = "Version of the embedding model")
