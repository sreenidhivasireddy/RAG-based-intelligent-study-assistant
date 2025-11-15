"""
DocumentVector repository - handles database operations for document vectors.

This module provides CRUD operations for DocumentVector model
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import delete
from app.models.document_vector import DocumentVector
from app.utils.logging import get_logger

logger = get_logger(__name__)


def create_document_vector(
    db: Session,
    file_md5: str,
    chunk_id: int,
    text_content: str,
    model_version: str = "default",
) -> DocumentVector:
    """
    Create a new document vector record.
    Equivalent to JpaRepository.save() for new entities.
    
    Args:
        db: Database session
        file_md5: MD5 hash of the file
        chunk_id: Chunk sequence number
        text_content: Text content of the chunk
        model_version: Embedding model version
        
    Returns:
        Created DocumentVector object
    """
    vector = DocumentVector(
        file_md5=file_md5,
        chunk_id=chunk_id,
        text_content=text_content,
        model_version=model_version,
    )
    
    db.add(vector)
    db.commit()
    db.refresh(vector)
    
    logger.debug(f"Created document vector: file_md5={file_md5}, chunk_id={chunk_id}")
    
    return vector


def get_document_vector_by_id(db: Session, vector_id: int) -> Optional[DocumentVector]:
    """
    Get a document vector by its primary key.
    
    Args:
        db: Database session
        vector_id: Primary key of the vector
        
    Returns:
        DocumentVector object if found, None otherwise
    """
    return db.query(DocumentVector).filter(DocumentVector.vector_id == vector_id).first()


def find_by_file_md5(db: Session, file_md5: str) -> List[DocumentVector]:
    """
    Find all document vectors for a specific file.
    
    Args:
        db: Database session
        file_md5: MD5 hash of the file
        
    Returns:
        List of DocumentVector objects, ordered by chunk_id
    """
    return (
        db.query(DocumentVector)
        .filter(DocumentVector.file_md5 == file_md5)
        .order_by(DocumentVector.chunk_id)
        .all()
    )


def delete_by_file_md5(db: Session, file_md5: str) -> int:
    """
    Delete all document vectors for a specific file.

    Args:
        db: Database session
        file_md5: MD5 hash of the file
        
    Returns:
        Number of deleted records
    """
    result = db.execute(
        delete(DocumentVector).where(DocumentVector.file_md5 == file_md5)
    )
    db.commit()
    
    deleted_count = result.rowcount
    logger.info(f"Deleted {deleted_count} document vectors for file_md5={file_md5}")
    
    return deleted_count


def count_by_file_md5(db: Session, file_md5: str) -> int:
    """
    Count the number of chunks for a specific file.
    
    Args:
        db: Database session
        file_md5: MD5 hash of the file
        
    Returns:
        Number of chunks
    """
    return db.query(DocumentVector).filter(DocumentVector.file_md5 == file_md5).count()


def update_document_vector(
    db: Session,
    vector_id: int,
    **kwargs
) -> Optional[DocumentVector]:
    """
    Update a document vector.
    
    Args:
        db: Database session
        vector_id: Primary key of the vector
        **kwargs: Fields to update
        
    Returns:
        Updated DocumentVector object if found, None otherwise
    """
    vector = get_document_vector_by_id(db, vector_id)
    
    if vector:
        for key, value in kwargs.items():
            if hasattr(vector, key):
                setattr(vector, key, value)
        
        db.commit()
        db.refresh(vector)
        logger.debug(f"Updated document vector: vector_id={vector_id}")
    
    return vector


def delete_document_vector(db: Session, vector_id: int) -> bool:
    """
    Delete a document vector by ID.  
    
    Args:
        db: Database session
        vector_id: Primary key of the vector
        
    Returns:
        True if deleted, False if not found
    """
    vector = get_document_vector_by_id(db, vector_id)
    
    if vector:
        db.delete(vector)
        db.commit()
        logger.debug(f"Deleted document vector: vector_id={vector_id}")
        return True
    
    return False


def get_all_document_vectors(
    db: Session,
    skip: int = 0,
    limit: int = 100
) -> List[DocumentVector]:
    """
    Get all document vectors with pagination.
    
    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of DocumentVector objects
    """
    return (
        db.query(DocumentVector)
        .order_by(DocumentVector.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def batch_create_document_vectors(
    db: Session,
    vectors: List[DocumentVector]
) -> List[DocumentVector]:
    """
    Batch create multiple document vectors.
    More efficient than creating one by one.
    
    Args:
        db: Database session
        vectors: List of DocumentVector objects to create
        
    Returns:
        List of created DocumentVector objects
    """
    db.add_all(vectors)
    db.commit()
    
    for vector in vectors:
        db.refresh(vector)
    
    logger.info(f"Batch created {len(vectors)} document vectors")
    
    return vectors