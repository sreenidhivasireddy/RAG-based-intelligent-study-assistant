"""
ChunkInfo ORM model for tracking file chunks in multi-part uploads.
"""

from sqlalchemy import Column, String, Integer, BigInteger
from app.database import Base


class ChunkInfo(Base):
    """Chunk information for multi-part file uploads."""
    __tablename__ = "chunk_info"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_md5 = Column(String(32), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_md5 = Column(String(32), nullable=False)
    storage_path = Column(String(255), nullable=False)


# TODO: Add TextChunk model if needed for text processing