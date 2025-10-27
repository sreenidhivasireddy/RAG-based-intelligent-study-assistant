"""
Upload API endpoints.
Provides REST APIs for multi-part file chunk upload with progress tracking.

API Endpoints:
- POST /api/v1/upload/chunk - Upload a single file chunk
- GET /api/v1/upload/status - Query upload progress and status
"""

from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from typing import Annotated

from app.database import SessionLocal
from app.schemas.upload import ChunkUploadRequest
from app.services.upload import upload_chunk_service, calculate_upload_progress
from app.repositories.upload_repository import get_file_upload


router = APIRouter(prefix="/upload", tags=["upload"])


# Dependency: Database session
def get_db():
    """Get database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/chunk")
async def upload_chunk(
    fileMd5: Annotated[str, Form(...)],
    chunkIndex: Annotated[int, Form(...)],
    totalSize: Annotated[int, Form(...)],
    fileName: Annotated[str, Form(...)],
    file: UploadFile = File(...),
    totalChunks: Annotated[int | None, Form()] = None,
    db: Session = Depends(get_db)
):
    """
    Upload a single file chunk.
    
    **URL**: `/api/v1/upload/chunk`  
    **Method**: `POST`  
    **Content-Type**: `multipart/form-data`
    
    **Required Fields**:
    - `fileMd5` (string): MD5 hash of complete file (32 characters)
    - `chunkIndex` (integer): Chunk index, 0-based (e.g., 0, 1, 2, ...)
    - `totalSize` (integer): Total file size in bytes
    - `fileName` (string): Original filename (supports Chinese/Unicode)
    - `file` (binary): Chunk binary data
    
    **Optional Fields**:
    - `totalChunks` (integer): Total number of chunks (auto-calculated if omitted)
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "Chunk uploaded successfully",
      "data": {
        "uploaded": [0, 1, 2, 3],
        "progress": 75.0
      }
    }
    ```
    
    **Response** (500 Error):
    ```json
    {
      "code": 500,
      "message": "Chunk upload failed: <error details>"
    }
    ```
    
    **Features**:
    - ✅ Idempotent: Re-uploading same chunk is safe
    - ✅ Automatic progress tracking via Redis bitmap
    - ✅ Chunk deduplication via MinIO verification
    - ✅ Supports resumable uploads 
    """
    try:
        # Auto-calculate totalChunks if not provided
        if totalChunks is None:
            # Try to infer from existing upload record
            file_record = get_file_upload(db, fileMd5)
            if file_record:
                from app.repositories.upload_repository import get_all_chunks
                chunks = get_all_chunks(db, fileMd5)
                if chunks:
                    totalChunks = max([c.chunk_index for c in chunks]) + 1
                else:
                    totalChunks = chunkIndex + 1
            else:
                totalChunks = chunkIndex + 1
        
        # Validate and create request object
        request = ChunkUploadRequest(
            file_md5=fileMd5,
            chunk_index=chunkIndex,
            total_chunks=totalChunks,
            file_name=fileName,
            total_size=totalSize
        )
        
        # Read chunk binary data
        file_data = await file.read()
        
        if len(file_data) == 0:
            return {
                "code": 500,
                "message": "Chunk data is empty"
            }
        
        # Process upload through service layer
        result = upload_chunk_service(db, request, file_data)
        
        # Return standardized response
        return {
            "code": 200,
            "message": "Chunk uploaded successfully",
            "data": {
                "uploaded": result.get("uploaded_chunks", []),
                "progress": result.get("progress", 0.0)
            }
        }
        
    except ValueError as e:
        # Pydantic validation errors
        return {
            "code": 500,
            "message": f"Chunk upload failed: {str(e)}"
        }
    except Exception as e:
        # Unexpected errors
        return {
            "code": 500,
            "message": f"Chunk upload failed: {str(e)}"
        }


@router.get("/status")
def get_upload_status(
    file_md5: str,
    total_chunks: int = None,
    db: Session = Depends(get_db)
):
    """
    Query upload status and progress for a file.
    
    **URL**: `/api/v1/upload/status`  
    **Method**: `GET`
    
    **Query Parameters**:
    - `file_md5` (required): MD5 hash of the file
    - `total_chunks` (optional): Total number of chunks for accurate progress calculation
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "Success",
      "data": {
        "uploaded": [0, 1, 2],
        "progress": 60.0,
        "total_chunks": 5
      }
    }
    ```
    
    **Response** (404 Not Found):
    ```json
    {
      "code": 404,
      "message": "Upload record not found"
    }
    ```
    
    **Use Cases**:
    - Resume upload progress after page refresh
    - Query missing chunks for resumable upload
    - Real-time progress bar updates
    """
    try:
        # Check if file upload record exists
        file_record = get_file_upload(db, file_md5)
        
        if not file_record:
            return {
                "code": 404,
                "message": "Upload record not found"
            }
        
        # Auto-detect total_chunks from database if not provided
        if total_chunks is None:
            from app.repositories.upload_repository import get_all_chunks
            chunks = get_all_chunks(db, file_md5)
            if chunks:
                # Infer from max chunk index + 1
                total_chunks = max([c.chunk_index for c in chunks]) + 1
            else:
                # No chunks yet, use 0
                total_chunks = 0
        
        # Calculate progress from Redis bitmap
        if total_chunks > 0:
            progress, uploaded = calculate_upload_progress(file_md5, total_chunks)
        else:
            progress = 0.0
            uploaded = []
        
        # Return standardized response
        return {
            "code": 200,
            "message": "Success",
            "data": {
                "uploaded": uploaded,
                "progress": round(progress, 1),
                "total_chunks": total_chunks
            }
        }
        
    except Exception as e:
        return {
            "code": 500,
            "message": f"Failed to get upload status: {str(e)}"
        }
