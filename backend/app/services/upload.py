"""
Service layer for file upload handling.
Implements chunk upload and progress tracking using MinIO + Redis + MySQL.

File Upload Flow (determined by frontend):
1. Frontend calculates file.name, file.size, and MD5 hash
2. Frontend splits file into chunks (configurable chunk size, e.g., 1MB, 5MB)
3. Frontend uploads chunks one by one
4. Backend tracks progress and merges chunks when complete
"""

import io
import hashlib
from sqlalchemy.orm import Session
from minio.error import S3Error

from app.clients.minio import minio_client, MINIO_BUCKET
from app.clients.redis import redis_client
from app.repositories.upload_repository import (
    get_file_upload,
    create_file_upload,
    chunk_exists,
    save_chunk_info,
    get_uploaded_chunk_count,
    update_file_status,
)
from app.schemas.upload import ChunkUploadRequest
from app.utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)


def is_chunk_uploaded_redis(file_md5: str, chunk_index: int) -> bool:
    """
    Check if chunk is marked as uploaded in Redis bitmap.
    
    Args:
        file_md5: MD5 hash of the file
        chunk_index: Index of the chunk
        
    Returns:
        True if chunk bit is set to 1, False otherwise
    """
    redis_key = f"upload:{file_md5}:chunks"
    return redis_client.getbit(redis_key, chunk_index) == 1


def mark_chunk_uploaded_redis(file_md5: str, chunk_index: int) -> None:
    """
    Mark a chunk as uploaded in Redis bitmap.
    
    Args:
        file_md5: MD5 hash of the file
        chunk_index: Index of the chunk
    """
    redis_key = f"upload:{file_md5}:chunks"
    redis_client.setbit(redis_key, chunk_index, 1)


def calculate_upload_progress(file_md5: str, total_chunks: int) -> tuple[float, list[int]]:
    """
    Calculate upload progress based on Redis bitmap.
    
    Args:
        file_md5: MD5 hash of the file
        total_chunks: Total number of chunks
        
    Returns:
        Tuple of (progress_percentage, list_of_uploaded_chunk_indices)
    """
    redis_key = f"upload:{file_md5}:chunks"
    uploaded = [i for i in range(total_chunks) if redis_client.getbit(redis_key, i)]
    progress = round(len(uploaded) / total_chunks * 100, 2) if total_chunks > 0 else 0.0
    return progress, uploaded


def upload_chunk_service(
    db: Session,
    request: ChunkUploadRequest,
    file_data: bytes
) -> dict:
    """
    Handle the complete upload process for a single chunk.
    
    Flow:
    1. Ensure file upload record exists in MySQL
    2. Check chunk status in Redis and MySQL
    3. Verify chunk exists in MinIO
    4. Upload chunk if not already uploaded
    5. Update Redis bitmap and MySQL record
    
    Args:
        db: Database session
        request: Validated chunk upload request containing metadata
        file_data: Binary content of the chunk
        
    Returns:
        Dict containing success status, message, and progress info
    """
    file_md5 = request.file_md5
    chunk_index = request.chunk_index
    
    # Step 1: Ensure file record exists in database
    file_record = get_file_upload(db, file_md5)
    if not file_record:
        create_file_upload(
            db,
            file_md5=file_md5,
            file_name=request.file_name,
            total_size=request.total_size
        )
    
    # Step 2: Check chunk upload status
    uploaded_in_redis = is_chunk_uploaded_redis(file_md5, chunk_index)
    exists_in_db = chunk_exists(db, file_md5, chunk_index)
    
    # Step 3: Verify chunk exists in MinIO storage
    chunk_verified = False
    if uploaded_in_redis:
        try:
            object_path = f"chunks/{file_md5}/{chunk_index}"
            minio_client.stat_object(MINIO_BUCKET, object_path)
            chunk_verified = True
            
            if exists_in_db:
                # Chunk is fully uploaded and recorded everywhere
                progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)
                return {
                    "success": True,
                    "message": "Chunk already exists, skipping upload",
                    "chunk_index": chunk_index,
                    "progress": progress,
                    "uploaded_chunks": uploaded_list
                }
        except S3Error:
            # Chunk not found in MinIO, need to re-upload
            chunk_verified = False
    
    # Step 4: Upload chunk if not verified
    if not chunk_verified:
        # Calculate chunk MD5
        chunk_md5 = hashlib.md5(file_data).hexdigest()
        object_path = f"chunks/{file_md5}/{chunk_index}"
        
        # Upload to MinIO
        minio_client.put_object(
            bucket_name=MINIO_BUCKET,
            object_name=object_path,
            data=io.BytesIO(file_data),
            length=len(file_data)
        )
        
        # Mark as uploaded in Redis
        mark_chunk_uploaded_redis(file_md5, chunk_index)
        
        # Save chunk info to database
        if not exists_in_db:
            save_chunk_info(db, file_md5, chunk_index, chunk_md5, object_path)
        
        # Calculate progress
        progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)
        
        return {
            "success": True,
            "message": f"Chunk {chunk_index} uploaded successfully",
            "chunk_index": chunk_index,
            "progress": progress,
            "uploaded_chunks": uploaded_list
        }
    
    # Fallback response
    progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)
    return {
        "success": True,
        "message": f"Chunk {chunk_index} already uploaded",
        "chunk_index": chunk_index,
        "progress": progress,
        "uploaded_chunks": uploaded_list
    }


def save_chunk(file_md5: str, chunk_index: int, file_data: bytes, total_chunks: int):
    """
    Legacy function: Save a file chunk to MinIO and record upload status in Redis.
    
    NOTE: This is the original implementation. Consider migrating to upload_chunk_service.
    
    Args:
        file_md5: Unique MD5 hash of the file
        chunk_index: Current chunk index
        file_data: Binary content of this chunk
        total_chunks: Total number of chunks
    """
    # Save to MinIO
    object_name = f"temp/{file_md5}/{chunk_index}"
    try:
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(file_data),
            length=len(file_data),
        )
        logger.info(f"Uploaded chunk {chunk_index} to MinIO ({object_name})")
    except Exception as e:
        raise Exception(f"Failed to upload chunk to MinIO: {e}")

    # Record upload status in Redis bitmap
    redis_key = f"upload:{file_md5}:chunks"
    redis_client.setbit(redis_key, chunk_index, 1)

    # Calculate progress
    uploaded = [i for i in range(total_chunks) if redis_client.getbit(redis_key, i)]
    progress = round(len(uploaded) / total_chunks * 100, 2)

    return {
        "uploaded": uploaded,
        "progress": progress,
    }

def save_chunk(file_md5: str, chunk_index: int, file_data: bytes, total_chunks: int):
    """
    Save a file chunk to MinIO and record upload status in Redis.

    Args:
        file_md5 (str): Unique MD5 hash of the file
        chunk_index (int): Current chunk index
        file_data (bytes): Binary content of this chunk
        total_chunks (int): Total number of chunks
    """
    # Save to MinIO
    object_name = f"temp/{file_md5}/{chunk_index}"
    try:
        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(file_data),
            length=len(file_data),
        )
        logger.info(f"Uploaded chunk {chunk_index} to MinIO ({object_name})")
    except Exception as e:
        raise Exception(f"Failed to upload chunk to MinIO: {e}")

    # Record upload status in Redis bitmap
    redis_key = f"upload:{file_md5}:chunks"
    redis_client.setbit(redis_key, chunk_index, 1)

    # Calculate progress
    uploaded = [i for i in range(total_chunks) if redis_client.getbit(redis_key, i)]
    progress = round(len(uploaded) / total_chunks * 100, 2)

    return {
        "uploaded": uploaded,
        "progress": progress,
    }