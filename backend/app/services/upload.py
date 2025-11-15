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
    get_all_chunks,
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


def merge_file_service(
    db: Session,
    file_md5: str,
    file_name: str
) -> dict:
    """
    Merge all uploaded file chunks into a single complete file.
    
    This is the final step of the multi-part upload workflow. It performs:
    1. Validation - Ensures file record exists in database
    2. Completeness check - Verifies all chunks are uploaded via Redis bitmap
    3. Chunk retrieval - Fetches chunk metadata from MySQL in correct order
    4. Binary merge - Downloads and concatenates all chunks from MinIO
    5. Final upload - Stores the complete file in permanent storage location
    6. Status update - Marks file as completed (status=1) in database
    7. (Optional) Event publishing - Triggers downstream parsing/indexing via Kafka
    
    Args:
        db: SQLAlchemy database session
        file_md5: MD5 hash of the complete file (used as unique identifier)
        file_name: Original filename (supports Unicode/Chinese characters)
        
    Returns:
        dict: Contains 'object_url' (final storage path) and 'file_size' (bytes)
        
    Raises:
        Exception: If file not found, chunks missing, or merge operation fails
        
    Example:
        >>> result = merge_file_service(db, "d41d8cd98f00b204e9800998ecf8427e", "annual-report.pdf")
        >>> print(result)
        {'object_url': 'documents/d41d8cd.../annual-report.pdf', 'file_size': 15728640}
    """
    
    # -------------------------------------------------------------------------
    # Step 1: Validate file exists in database
    # -------------------------------------------------------------------------
    # Why: Ensure this file_md5 was previously registered during chunk uploads
    # Without this record, we have no metadata to work with
    file_record = get_file_upload(db, file_md5)
    if not file_record:
        raise Exception("File not found in database. Please upload chunks first.")
    
    # -------------------------------------------------------------------------
    # Step 2: Retrieve all chunk metadata from MySQL
    # -------------------------------------------------------------------------
    # Why: We need to know:
    #   - How many chunks exist (total_chunks)
    #   - Each chunk's storage_path in MinIO
    #   - The correct order (chunk_index) for concatenation
    chunks = get_all_chunks(db, file_md5)
    total_chunks = len(chunks)
    
    if total_chunks == 0:
        raise Exception("No chunks found in database. Upload at least one chunk first.")
    
    # -------------------------------------------------------------------------
    # Step 3: Verify all chunks are uploaded (Redis bitmap check)
    # -------------------------------------------------------------------------
    # Why: Redis bitmap tracks upload completion in O(1) time per chunk
    # Even if DB has chunk records, we validate that Redis confirms upload success
    # This prevents merging incomplete uploads
    redis_key = f"upload:{file_md5}:chunks"
    uploaded_bits = [
        redis_client.getbit(redis_key, i)
        for i in range(total_chunks)
    ]
    
    if not all(uploaded_bits):
        # Find which chunks are missing
        missing_chunks = [i for i, bit in enumerate(uploaded_bits) if bit == 0]
        raise Exception(
            f"Not all chunks have been uploaded. Missing chunks: {missing_chunks}. "
            f"Upload progress: {sum(uploaded_bits)}/{total_chunks}"
        )
    
    # -------------------------------------------------------------------------
    # Step 4: Download and merge all chunks from MinIO
    # -------------------------------------------------------------------------
    # Why: Chunks are stored separately; we need to concatenate them in order
    # to reconstruct the original file
    # 
    # Performance note: For files < 200MB, in-memory merge is acceptable
    # For larger files, consider streaming to temporary file to avoid OOM
    logger.info(f"Starting merge for file {file_md5} with {total_chunks} chunks")
    merged_bytes = b""
    
    for chunk in chunks:
        try:
            # Download chunk from MinIO
            obj = minio_client.get_object(
                MINIO_BUCKET,
                chunk.storage_path
            )
            chunk_data = obj.read()
            merged_bytes += chunk_data
            
            logger.info(
                f"Merged chunk {chunk.chunk_index}/{total_chunks - 1} "
                f"(size: {len(chunk_data)} bytes)"
            )
            
        except Exception as e:
            raise Exception(
                f"Failed to download chunk {chunk.chunk_index} from MinIO: {e}"
            )
    
    # -------------------------------------------------------------------------
    # Step 5: Upload merged file to final storage location
    # -------------------------------------------------------------------------
    # Why: Temporary chunks live in /chunks/{md5}/{index}
    # Final complete file should be stored in a permanent, organized location
    # Pattern: documents/{file_md5}/{filename} enables:
    #   - Easy retrieval by MD5
    #   - Preserves original filename (important for downloads)
    #   - Separates temporary vs permanent storage
    final_path = f"documents/{file_md5}/{file_name}"
    
    try:
        minio_client.put_object(
            MINIO_BUCKET,
            final_path,
            io.BytesIO(merged_bytes),
            length=len(merged_bytes)
        )
        logger.info(f"Merged file uploaded to MinIO: {final_path} ({len(merged_bytes)} bytes)")
        
    except Exception as e:
        raise Exception(f"Failed to upload merged file to MinIO: {e}")
    
    # -------------------------------------------------------------------------
    # Step 6: Update file status in MySQL (0 -> 2)
    # -------------------------------------------------------------------------
    # Why: Status field tracks complete lifecycle:
    #   - status=0: Upload in progress (chunks being received)
    #   - status=2: File merged, waiting for parsing/indexing
    #   - status=1: Fully completed (parsed, vectorized, indexed, searchable)
    # 
    # Important: status=1 should ONLY be set by the parsing service after:
    #   1. PDF/Word text extraction succeeds
    #   2. Text chunking and embedding generation succeeds
    #   3. Vector data is successfully written to Elasticsearch
    #   4. File becomes searchable in the knowledge base
    # 
    # This ensures status=1 means "ready for user queries", not just "uploaded"
    update_file_status(db, file_md5, status=2)
    logger.info(f"File {file_md5} status updated to merged (status=2), pending parsing")
    
    # -------------------------------------------------------------------------
    # Step 7 (Optional): Publish Kafka event for downstream processing
    # -------------------------------------------------------------------------
    # Why: Decouples upload from parsing/indexing workflow
    # After successful merge, trigger:
    #   - PDF text extraction
    #   - Vector embedding generation
    #   - Elasticsearch indexing
    #   - Thumbnail generation
    # 
    # Uncomment when Kafka producer is configured:
    # try:
    #     kafka_producer.send("file-parse-topic", {
    #         "file_md5": file_md5,
    #         "file_name": file_name,
    #         "storage_path": final_path,
    #         "file_size": len(merged_bytes)
    #     })
    #     logger.info(f"Published parse event to Kafka for file {file_md5}")
    # except Exception as e:
    #     logger.warning(f"Failed to publish Kafka event: {e}")
    
    # -------------------------------------------------------------------------
    # Step 8 (Optional): Cleanup temporary chunk files
    # -------------------------------------------------------------------------
    # Why: Save storage space by removing temporary chunks after successful merge
    # 
    # Trade-offs:
    #   - Immediate cleanup: Saves space but prevents re-merge if needed
    #   - Delayed cleanup: Use cron job or TTL policy (recommended)
    # 
    # Uncomment for immediate cleanup:
    # try:
    #     for chunk in chunks:
    #         minio_client.remove_object(MINIO_BUCKET, chunk.storage_path)
    #     logger.info(f"Cleaned up {total_chunks} temporary chunks for {file_md5}")
    # except Exception as e:
    #     logger.warning(f"Failed to cleanup chunks: {e}")
    
    # Return final file information
    return {
        "object_url": final_path,
        "file_size": len(merged_bytes)
    }
