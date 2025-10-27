"""
FileUpload ORM model for tracking uploaded files.
"""

from sqlalchemy import Column, String, Integer, BigInteger, TIMESTAMP
from sqlalchemy.sql import func
from app.database import Base


class FileUpload(Base):
    """File upload metadata table."""
    __tablename__ = "file_upload"

    file_md5 = Column(String(32), primary_key=True, comment='MD5 hash of the file, used as unique identifier')
    file_name = Column(String(255), nullable=False, comment='Original file name')
    total_size = Column(BigInteger, nullable=False, comment='Total file size in bytes')
    status = Column(Integer, nullable=False, default=0, comment='Upload status: 0 - uploading, 1 - completed')
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), comment='File upload creation timestamp')
    merged_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment='File merge completion timestamp')
