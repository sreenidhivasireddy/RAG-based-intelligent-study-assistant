"""
Documents API endpoints.
Provides REST APIs for managing and querying uploaded documents.

API Endpoints:
- GET /api/v1/documents/uploads - Get list of all uploaded files
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.schemas.upload import FileListResponse, FileUploadItem
from app.repositories.upload_repository import get_all_file_uploads, get_file_upload_count


router = APIRouter(prefix="/documents", tags=["documents"])


# Dependency: Database session
def get_db():
    """Get database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/uploads", response_model=FileListResponse)
def get_uploads_list(
    db: Session = Depends(get_db)
):
    """
    Get list of all merged files (status=1 or status=2).
    
    Returns all files that have been successfully merged:
    - status=2: Merged, waiting for parsing
    - status=1: Completed (parsed, indexed, searchable)
    
    **URL**: `/api/v1/documents/uploads`  
    **Method**: `GET`
    
    **No parameters required**
    
    **Response** (200 OK):
    ```json
    {
      "status": "success",
      "data": [
        {
          "fileMd5": "a1b2c3d4e5f6g7h8i9j0",
          "fileName": "example-document.pdf",
          "totalSize": 1048576,
          "status": 2,
          "createdAt": "2023-10-01T10:30:00",
          "mergedAt": "2023-10-01T10:35:00"
        }
      ]
    }
    ```
    
    **Response** (500 Error):
    ```json
    {
      "status": "error",
      "message": "Failed to get file list: <error details>"
    }
    ```
    
    **Status field meaning**:
    - `0` = Uploading (chunks being received) ← **Not returned**
    - `2` = Merged (waiting for parsing) ← **Returned**
    - `1` = Completed (parsed, indexed, searchable) ← **Returned**
    - ✅ Pagination support for large file lists
    **Use Cases**:
    - Get all files ready for parsing (parsing service consumer queue)
    - Monitor which files are waiting for text extraction
    - Display all processed files (merged or completed)
    - Debug parsing pipeline
    """
    try:
        # Get all files with status=1 or status=2
        # We need to query twice and combine results, or modify repository function
        files_merged = get_all_file_uploads(
            db=db,
            skip=0,
            limit=1000,
            status_filter=2  # Merged files
        )
        
        files_completed = get_all_file_uploads(
            db=db,
            skip=0,
            limit=1000,
            status_filter=1  # Completed files
        )
        
        # Combine both lists
        all_files = list(files_merged) + list(files_completed)
        
        # Sort by created_at descending (newest first)
        all_files.sort(key=lambda x: x.created_at, reverse=True)
        
        # Convert ORM objects to response models
        file_items = [
            FileUploadItem(
                fileMd5=f.file_md5,
                fileName=f.file_name,
                totalSize=f.total_size,
                status=f.status,
                createdAt=f.created_at,
                mergedAt=f.merged_at
            )
            for f in all_files
        ]
        
        # Return standardized response
        return FileListResponse(
            status="success",
            data=file_items
        )
        
    except Exception as e:
        # Handle errors gracefully
        return FileListResponse(
            status="error",
            data=[],
            message=f"Failed to get file list: {str(e)}"
        )
