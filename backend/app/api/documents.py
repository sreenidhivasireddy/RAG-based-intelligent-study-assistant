"""
Documents API endpoints.
Provides REST APIs for managing and querying uploaded documents.

API Endpoints:
- GET /api/v1/documents/uploads - Get list of all uploaded files
- GET /api/v1/documents/{file_md5}/status - Check file processing status
- GET /api/v1/documents/{file_md5}/content - Get file content directly
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy import delete
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

from app.database import SessionLocal
from app.schemas.upload import FileListResponse, FileUploadItem
from app.repositories.upload_repository import get_all_file_uploads, get_file_upload_count, get_file_upload
from app.services.file_content_service import FileContentService
from app.utils.logging import get_logger
from app.services.azure_search_service import AzureSearchService
from app.clients.azure_search import get_azure_search_client
from app.services.blob_storage import blob_storage_client
from app.clients.redis import redis_client
from app.models.document_vector import DocumentVector
from app.models.chunk import ChunkInfo
from app.models.file_upload import FileUpload
from app.models.synthetic_eval_dataset import SyntheticEvalDataset
import os

logger = get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# Dependency: Database session
def get_db():
    """Get database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _generate_sas_url_for_blob(blob_name: str) -> str:
    if not blob_name:
        return blob_name

    if blob_name.startswith("http://") or blob_name.startswith("https://"):
        return blob_name

    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    if not conn_str:
        return blob_name

    try:
        blob_service_client = BlobServiceClient.from_connection_string(conn_str)
        account_name = blob_service_client.account_name
        account_key = None
        if "AccountKey=" in conn_str:
            account_key = conn_str.split("AccountKey=")[1].split(";")[0]

        if not account_name or not account_key:
            return blob_name

        container = os.getenv("AZURE_STORAGE_CONTAINER", "documents")
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=7),
        )
        return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"
    except Exception as e:
        logger.warning(f"Failed to generate SAS URL for {blob_name}: {e}")
        return blob_name


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

@router.get("/{file_md5}/open-url")
def get_file_open_url(
    file_md5: str,
    db: Session = Depends(get_db)
):
    """
    Return an openable URL (SAS) for the uploaded file.
    """
    file_record = get_file_upload(db, file_md5)
    if not file_record:
        raise HTTPException(status_code=404, detail=f"File not found: {file_md5}")

    blob_path = f"documents/{file_md5}/{file_record.file_name}"
    if not blob_storage_client.exists(blob_path):
        raise HTTPException(status_code=404, detail=f"Blob not found for file: {file_md5}")

    return {
        "code": 200,
        "message": "Success",
        "data": {
            "fileMd5": file_md5,
            "fileName": file_record.file_name,
            "url": _generate_sas_url_for_blob(blob_path),
            "blobPath": blob_path,
        }
    }


@router.get("/{file_md5}/status")
def get_file_processing_status(
    file_md5: str,
    db: Session = Depends(get_db)
):
    """
    Check the processing status of an uploaded file.
    
    **URL**: `/api/v1/documents/{file_md5}/status`  
    **Method**: `GET`
    
    **URL Parameters**:
    - `file_md5` (string): MD5 hash of the file (32 characters)
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "Success",
      "data": {
        "fileMd5": "a1b2c3d4e5f6g7h8i9j0",
        "fileName": "example.pdf",
        "status": 1,
        "statusText": "completed",
        "totalSize": 1048576,
        "createdAt": "2023-10-01T10:30:00",
        "mergedAt": "2023-10-01T10:35:00",
        "notes": "File is indexed and ready for search"
      }
    }
    ```
    
    **Status values**:
    - `0` = Uploading (chunks being received)
    - `2` = Merged (waiting for processing)
    - `1` = Completed (indexed, ready for search)
    
    **Response** (404 Not Found):
    ```json
    {
      "code": 404,
      "message": "File not found"
    }
    ```
    """
    try:
        file_record = get_file_upload(db, file_md5)
        if not file_record:
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_md5}"
            )
        
        status_map = {
            0: "uploading",
            1: "completed",
            2: "merged"
        }
        
        return {
            "code": 200,
            "message": "Success",
            "data": {
                "fileMd5": file_record.file_md5,
                "fileName": file_record.file_name,
                "status": file_record.status,
                "statusText": status_map.get(file_record.status, "unknown"),
                "totalSize": file_record.total_size,
                "createdAt": file_record.created_at,
                "mergedAt": file_record.merged_at,
                "notes": "File is indexed and ready for search" if file_record.status == 1 
                         else "File is waiting to be processed" if file_record.status == 2
                         else "File is still being uploaded"
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking file status for {file_md5}: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"Error: {str(e)}"
        }


@router.get("/{file_md5}/content")
def get_file_content(
    file_md5: str,
    db: Session = Depends(get_db)
):
    """
    Retrieve the raw content of an uploaded file directly.
    
    **This is a fallback endpoint** - useful when search index is unavailable or incomplete.
    
    **URL**: `/api/v1/documents/{file_md5}/content`  
    **Method**: `GET`
    
    **URL Parameters**:
    - `file_md5` (string): MD5 hash of the file
    
    **Query Parameters**:
    - `max_length` (integer, optional): Maximum length of content to return (default: 5000)
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "Success",
      "data": {
        "fileMd5": "a1b2c3d4e5f6g7h8i9j0",
        "fileName": "example.pdf",
        "content": "The content of the file...",
        "contentLength": 1234,
        "contentTruncated": false
      }
    }
    ```
    
    **Response** (404 Not Found):
    ```json
    {
      "code": 404,
      "message": "File not found"
    }
    ```
    
    **Use Cases**:
    - Fallback when search index is incomplete
    - Direct file content access for debugging
    - Getting full file content for offline processing
    """
    try:
        file_record = get_file_upload(db, file_md5)
        if not file_record:
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_md5}"
            )
        
        # Use FileContentService to retrieve content
        file_content_service = FileContentService()
        content = file_content_service.get_file_content_by_md5(file_md5, db)
        
        if not content:
            return {
                "code": 404,
                "message": f"Could not retrieve content for file {file_md5}. File may still be processing.",
                "data": None
            }
        
        return {
            "code": 200,
            "message": "Success",
            "data": {
                "fileMd5": file_md5,
                "fileName": file_record.file_name,
                "content": content,
                "contentLength": len(content),
                "contentTruncated": False
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving file content for {file_md5}: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"Error: {str(e)}"
        }


@router.post("/{file_md5}/process")
def manually_trigger_file_processing(
    file_md5: str,
    db: Session = Depends(get_db)
):
    """
    Manually trigger file processing and indexing.
    
    **Use when**: File has been uploaded but processing hasn't started or failed.
    
    **URL**: `/api/v1/documents/{file_md5}/process`  
    **Method**: `POST`
    
    **URL Parameters**:
    - `file_md5` (string): MD5 hash of the file
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "File processing triggered successfully",
      "data": {
        "fileMd5": "a1b2c3d4e5f6g7h8i9j0",
        "fileName": "example.pdf",
        "status": "processing_queued"
      }
    }
    ```
    
    **Response** (400 Bad Request):
    ```json
    {
      "code": 400,
      "message": "File is already completed or processing"
    }
    ```
    """
    try:
        file_record = get_file_upload(db, file_md5)
        if not file_record:
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_md5}"
            )
        
        if file_record.status == 1:  # Already completed
            return {
                "code": 400,
                "message": "File is already completed and indexed",
                "data": {
                    "fileMd5": file_md5,
                    "fileName": file_record.file_name,
                    "status": "completed"
                }
            }
        
        # Queue file for processing by publishing Kafka message
        logger.info(f"Manually triggering processing for file: {file_md5}")
        
        from app.services.upload import _publish_file_processing_event
        
        try:
            _publish_file_processing_event(
                file_md5=file_md5,
                file_name=file_record.file_name,
                file_path=f"documents/{file_md5}/{file_record.file_name}"
            )
            
            return {
                "code": 200,
                "message": "File processing triggered successfully",
                "data": {
                    "fileMd5": file_md5,
                    "fileName": file_record.file_name,
                    "status": "processing_queued"
                }
            }
        except Exception as kafka_error:
            logger.error(f"Failed to publish Kafka message: {kafka_error}")
            return {
                "code": 500,
                "message": f"Failed to queue file: {str(kafka_error)}"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering file processing for {file_md5}: {e}", exc_info=True)
        return {
            "code": 500,
            "message": f"Error: {str(e)}"
        }


@router.delete("/{file_md5}")
def delete_uploaded_file(
    file_md5: str,
    db: Session = Depends(get_db)
):
    """
    Delete uploaded file and associated metadata/chunks/vectors.
    """
    file_record = get_file_upload(db, file_md5)
    if not file_record:
        raise HTTPException(status_code=404, detail=f"File not found: {file_md5}")

    file_name = file_record.file_name
    document_blob = f"documents/{file_md5}/{file_name}"

    chunk_paths = [
        c.storage_path
        for c in db.query(ChunkInfo).filter(ChunkInfo.file_md5 == file_md5).all()
        if getattr(c, "storage_path", None)
    ]

    deleted_blobs = []
    failed_blob_deletes = []

    try:
        if blob_storage_client.exists(document_blob):
            blob_storage_client.delete(document_blob)
            deleted_blobs.append(document_blob)
    except Exception as e:
        failed_blob_deletes.append({"path": document_blob, "error": str(e)})

    for chunk_path in chunk_paths:
        try:
            if blob_storage_client.exists(chunk_path):
                blob_storage_client.delete(chunk_path)
                deleted_blobs.append(chunk_path)
        except Exception as e:
            failed_blob_deletes.append({"path": chunk_path, "error": str(e)})

    vectors_deleted = db.execute(
        delete(DocumentVector).where(DocumentVector.file_md5 == file_md5)
    ).rowcount or 0
    synthetic_deleted = db.execute(
        delete(SyntheticEvalDataset).where(SyntheticEvalDataset.document_id == file_md5)
    ).rowcount or 0
    chunks_deleted = db.execute(
        delete(ChunkInfo).where(ChunkInfo.file_md5 == file_md5)
    ).rowcount or 0
    file_deleted = db.execute(
        delete(FileUpload).where(FileUpload.file_md5 == file_md5)
    ).rowcount or 0
    db.commit()

    try:
        if redis_client is not None:
            redis_client.delete(f"upload:{file_md5}:chunks")
    except Exception as e:
        logger.warning(f"Failed to clear upload bitmap for {file_md5}: {e}")

    search_delete = {"success": False, "deleted": 0, "error": None}
    try:
        search_client = get_azure_search_client()
        azure_search_service = AzureSearchService(search_client)
        search_delete = azure_search_service.delete_by_file_md5(file_md5)
    except Exception as e:
        logger.warning(f"Failed to delete Azure Search docs for {file_md5}: {e}")
        search_delete = {"success": False, "deleted": 0, "error": str(e)}

    return {
        "code": 200,
        "message": "File deleted successfully",
        "data": {
            "fileMd5": file_md5,
            "fileName": file_name,
            "deletedRecords": {
                "file_upload": file_deleted,
                "chunk_info": chunks_deleted,
                "document_vectors": vectors_deleted,
                "synthetic_eval_dataset": synthetic_deleted,
            },
            "searchIndexDelete": search_delete,
            "deletedBlobCount": len(deleted_blobs),
            "failedBlobDeletes": failed_blob_deletes
        }
    }


@router.get("/debug/{file_md5}")
def debug_doc_pipeline(file_md5: str, db: Session = Depends(get_db)):
    """
    Debug endpoint to check pipeline for a given file_md5.
    Returns: blob exists?, blob path, parsed preview (first 500 chars if available), azure search doc count for this file.
    """
    if os.getenv("DEBUG", "false").lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Debug endpoints are disabled")

    file_record = get_file_upload(db, file_md5)
    if not file_record:
        raise HTTPException(status_code=404, detail=f"File not found: {file_md5}")

    blob_path = f"documents/{file_md5}/{file_record.file_name}"
    blob_exists = False
    try:
        blob_exists = blob_storage_client.exists(blob_path)
    except Exception as e:
        logger.warning(f"Blob existence check failed: {e}")

    # parsed preview
    file_content_service = FileContentService()
    parsed = file_content_service.get_file_content_by_md5(file_md5, db)
    parsed_preview = parsed[:500] if parsed else None

    # azure search count
    try:
        search_client = get_azure_search_client()
        azure_search_service = AzureSearchService(search_client)
        doc_count = azure_search_service.count_documents(file_md5)
    except Exception as e:
        logger.warning(f"Azure search check failed: {e}")
        doc_count = -1

    return {
        "fileMd5": file_md5,
        "fileName": file_record.file_name,
        "blobPath": blob_path,
        "blobExists": blob_exists,
        "parsedPreview": parsed_preview,
        "azureSearchDocCount": doc_count
    }
