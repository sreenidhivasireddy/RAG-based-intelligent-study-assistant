"""
Upload repository - handles database operations for file uploads and chunks.

This module provides CRUD operations for FileUpload and ChunkInfo models.
It should be used by the service layer (app.services.upload) for persistence.
"""

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.models import FileUpload, ChunkInfo
from app.models.document_vector import DocumentVector


def get_file_upload(db: Session, file_md5: str) -> FileUpload | None:
    """
    Retrieve a file upload record by MD5 hash.

    Args:
        db: Database session
        file_md5: MD5 hash of the file

    Returns:
        FileUpload object if found, None otherwise
    """
    return db.query(FileUpload).filter(FileUpload.file_md5 == file_md5).first()


def create_file_upload(
    db: Session,
    file_md5: str,
    file_name: str,
    total_size: int,
) -> FileUpload:
    """
    Create a new file upload record.

    Args:
        db: Database session
        file_md5: MD5 hash of the file
        file_name: Original filename
        total_size: Total file size in bytes

    Returns:
        Created FileUpload object
    """
    file = FileUpload(
        file_md5=file_md5,
        file_name=file_name,
        total_size=total_size,
        status=0,  # 0 = uploading
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    return file


def update_file_status(db: Session, file_md5: str, status: int) -> FileUpload | None:
    """
    Update the status of a file upload.

    Args:
        db: Database session
        file_md5: MD5 hash of the file
        status: New status (0=uploading, 1=done)

    Returns:
        Updated FileUpload object if found, None otherwise
    """
    file = get_file_upload(db, file_md5)
    if file:
        file.status = status
        db.commit()
        db.refresh(file)
    return file


def chunk_exists(db: Session, file_md5: str, chunk_index: int) -> bool:
    """
    Check if a specific chunk has already been uploaded.

    Args:
        db: Database session
        file_md5: MD5 hash of the file
        chunk_index: Index of the chunk

    Returns:
        True if chunk exists, False otherwise
    """
    return (
        db.query(ChunkInfo)
        .filter(
            ChunkInfo.file_md5 == file_md5,
            ChunkInfo.chunk_index == chunk_index,
        )
        .first()
        is not None
    )


def save_chunk_info(
    db: Session,
    file_md5: str,
    chunk_index: int,
    chunk_md5: str,
    storage_path: str,
) -> ChunkInfo:
    """
    Save chunk metadata to database.

    Args:
        db: Database session
        file_md5: MD5 hash of the file
        chunk_index: Index of this chunk
        chunk_md5: MD5 hash of this chunk
        storage_path: MinIO/storage path where chunk is stored

    Returns:
        Created ChunkInfo object
    """
    chunk = ChunkInfo(
        file_md5=file_md5,
        chunk_index=chunk_index,
        chunk_md5=chunk_md5,
        storage_path=storage_path,
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def get_all_chunks(db: Session, file_md5: str) -> list[ChunkInfo]:
    """
    Get all chunks for a specific file, ordered by chunk_index.

    Args:
        db: Database session
        file_md5: MD5 hash of the file

    Returns:
        List of ChunkInfo objects
    """
    return (
        db.query(ChunkInfo)
        .filter(ChunkInfo.file_md5 == file_md5)
        .order_by(ChunkInfo.chunk_index)
        .all()
    )


def get_uploaded_chunk_count(db: Session, file_md5: str) -> int:
    """
    Count how many chunks have been uploaded for a file.

    Args:
        db: Database session
        file_md5: MD5 hash of the file

    Returns:
        Number of uploaded chunks
    """
    return db.query(ChunkInfo).filter(ChunkInfo.file_md5 == file_md5).count()


def get_all_file_uploads(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: int = None
) -> list[FileUpload]:
    """
    Retrieve all file upload records with optional pagination and filtering.
    
    Args:
        db: Database session
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
        status_filter: Optional status filter (0=uploading, 2=merged, 1=completed)
        
    Returns:
        List of FileUpload objects ordered by creation time (newest first)
    """
    query = db.query(FileUpload)
    
    # Apply status filter if provided
    if status_filter is not None:
        query = query.filter(FileUpload.status == status_filter)
    
    # Order by creation time descending (newest first)
    query = query.order_by(FileUpload.created_at.desc())
    
    # Apply pagination
    return query.offset(skip).limit(limit).all()


def get_file_upload_count(db: Session, status_filter: int = None) -> int:
    """
    Count total number of file uploads with optional status filter.
    
    Args:
        db: Database session
        status_filter: Optional status filter
        
    Returns:
        Total count of file uploads
    """
    query = db.query(FileUpload)
    
    if status_filter is not None:
        query = query.filter(FileUpload.status == status_filter)
    
    return query.count()


def get_file_uploads_with_vectors(
    db: Session,
    limit: int = 100,
) -> list[FileUpload]:
    """
    Return uploaded files that have at least one parsed chunk in document_vectors.
    This is the valid source set for synthetic evaluation generation because the
    synthetic_eval_dataset table has a foreign key to file_upload.
    """
    subquery = (
        db.query(distinct(DocumentVector.file_md5).label("file_md5"))
        .subquery()
    )
    return (
        db.query(FileUpload)
        .join(subquery, FileUpload.file_md5 == subquery.c.file_md5)
        .order_by(FileUpload.created_at.desc())
        .limit(limit)
        .all()
    )
