"""
Service layer for file upload handling.
Implements chunk upload and progress tracking using Azure Blob Storage + Redis + MySQL.
"""

import io
import hashlib
import json
import os
from sqlalchemy.orm import Session
from azure.core.exceptions import AzureError

from app.services.blob_storage import blob_storage_client
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

# ✅ Kafka
from kafka import KafkaProducer
from app.clients.kafka import KafkaConfig

logger = get_logger(__name__)

# -------------------------------------------------------------------
# ✅ Kafka Producer (singleton for this module)
# -------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
FILE_PROCESSING_TOPIC = os.getenv("FILE_PROCESSING_TOPIC", "file-processing-topic1")

_kafka_producer = None


def _get_kafka_producer() -> KafkaProducer:
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = KafkaProducer(
            bootstrap_servers=[s.strip() for s in KAFKA_BOOTSTRAP_SERVERS.split(",")],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: str(k).encode("utf-8"),
            retries=3,
        )
        logger.info(f"✓ Kafka Producer initialized: {KAFKA_BOOTSTRAP_SERVERS}")
    return _kafka_producer


def _publish_file_processing_event(file_md5: str, file_name: str, file_path: str) -> None:
    """
    Publish downstream processing event to Kafka.
    Consumer expects: file_md5, file_name, file_path
    """
    producer = _get_kafka_producer()

    payload = {
        "file_md5": file_md5,
        "file_name": file_name,
        "file_path": file_path,  # can be blob URL OR blob path; your consumer supports remote URL
    }

    try:
        topic = KafkaConfig.get_file_processing_topic()
    except Exception:
        topic = FILE_PROCESSING_TOPIC

    logger.info(f"Publishing file processing event to Kafka topic={topic} file_md5={file_md5}")
    future = producer.send(
        topic,
        key=file_md5,
        value=payload
    )
    # Block briefly to surface errors immediately
    future.get(timeout=10)
    producer.flush()


def is_chunk_uploaded_redis(file_md5: str, chunk_index: int) -> bool:
    redis_key = f"upload:{file_md5}:chunks"
    return redis_client.getbit(redis_key, chunk_index) == 1


def mark_chunk_uploaded_redis(file_md5: str, chunk_index: int) -> None:
    redis_key = f"upload:{file_md5}:chunks"
    redis_client.setbit(redis_key, chunk_index, 1)


def calculate_upload_progress(file_md5: str, total_chunks: int) -> tuple[float, list[int]]:
    redis_key = f"upload:{file_md5}:chunks"
    uploaded = [i for i in range(total_chunks) if redis_client.getbit(redis_key, i)]
    progress = round(len(uploaded) / total_chunks * 100, 2) if total_chunks > 0 else 0.0
    return progress, uploaded


def upload_chunk_service(
    db: Session,
    request: ChunkUploadRequest,
    file_data: bytes
) -> dict:
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

    # Step 3: Verify chunk exists in Azure Blob Storage
    chunk_verified = False
    if uploaded_in_redis:
        try:
            blob_path = f"chunks/{file_md5}/{chunk_index}"
            blob_storage_client.stat_object(blob_path)
            chunk_verified = True

            if exists_in_db:
                progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)
                return {
                    "success": True,
                    "message": "Chunk already exists, skipping upload",
                    "chunk_index": chunk_index,
                    "progress": progress,
                    "uploaded_chunks": uploaded_list
                }
        except AzureError:
            chunk_verified = False

    # Step 4: Upload chunk if not verified
    if not chunk_verified:
        chunk_md5 = hashlib.md5(file_data).hexdigest()
        blob_path = f"chunks/{file_md5}/{chunk_index}"

        blob_storage_client.upload_bytes(
            blob_name=blob_path,
            data=file_data,
            content_type="application/octet-stream"
        )

        mark_chunk_uploaded_redis(file_md5, chunk_index)

        if not exists_in_db:
            save_chunk_info(db, file_md5, chunk_index, chunk_md5, blob_path)

        progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)

        return {
            "success": True,
            "message": f"Chunk {chunk_index} uploaded successfully",
            "chunk_index": chunk_index,
            "progress": progress,
            "uploaded_chunks": uploaded_list
        }

    progress, uploaded_list = calculate_upload_progress(file_md5, request.total_chunks)
    return {
        "success": True,
        "message": f"Chunk {chunk_index} already uploaded",
        "chunk_index": chunk_index,
        "progress": progress,
        "uploaded_chunks": uploaded_list
    }


def save_chunk(file_md5: str, chunk_index: int, file_data: bytes, total_chunks: int):
    blob_name = f"temp/{file_md5}/{chunk_index}"
    try:
        blob_storage_client.upload_bytes(
            blob_name=blob_name,
            data=file_data,
            content_type="application/octet-stream"
        )
        logger.info(f"Uploaded chunk {chunk_index} to Azure Blob Storage ({blob_name})")
    except Exception as e:
        raise Exception(f"Failed to upload chunk to Azure Blob Storage: {e}")

    redis_key = f"upload:{file_md5}:chunks"
    redis_client.setbit(redis_key, chunk_index, 1)

    uploaded = [i for i in range(total_chunks) if redis_client.getbit(redis_key, i)]
    progress = round(len(uploaded) / total_chunks * 100, 2)

    return {"uploaded": uploaded, "progress": progress}


def merge_file_service(
    db: Session,
    file_md5: str,
    file_name: str
) -> dict:
    file_record = get_file_upload(db, file_md5)
    if not file_record:
        raise Exception("File not found in database. Please upload chunks first.")

    chunks = get_all_chunks(db, file_md5)
    total_chunks = len(chunks)
    if total_chunks == 0:
        raise Exception("No chunks found in database. Upload at least one chunk first.")

    redis_key = f"upload:{file_md5}:chunks"
    uploaded_bits = [redis_client.getbit(redis_key, i) for i in range(total_chunks)]
    if not all(uploaded_bits):
        missing_chunks = [i for i, bit in enumerate(uploaded_bits) if bit == 0]
        raise Exception(
            f"Not all chunks have been uploaded. Missing chunks: {missing_chunks}. "
            f"Upload progress: {sum(uploaded_bits)}/{total_chunks}"
        )

    logger.info(f"Starting merge for file {file_md5} with {total_chunks} chunks")
    merged_bytes = b""

    for chunk in chunks:
        try:
            chunk_data = blob_storage_client.download_bytes(chunk.storage_path)
            merged_bytes += chunk_data
            logger.info(
                f"Merged chunk {chunk.chunk_index}/{total_chunks - 1} "
                f"(size: {len(chunk_data)} bytes)"
            )
        except Exception as e:
            raise Exception(
                f"Failed to download chunk {chunk.chunk_index} from Azure Blob Storage: {e}"
            )

    final_path = f"documents/{file_md5}/{file_name}"

    try:
        blob_storage_client.upload_bytes(
            blob_name=final_path,
            data=merged_bytes,
            content_type="application/octet-stream"
        )
        logger.info(f"Merged file uploaded to Azure Blob Storage: {final_path} ({len(merged_bytes)} bytes)")
    except Exception as e:
        raise Exception(f"Failed to upload merged file to Azure Blob Storage: {e}")

    # status=2 means merged, pending parsing
    update_file_status(db, file_md5, status=2)
    logger.info(f"File {file_md5} status updated to merged (status=2), pending parsing")
    # Publish processing event so consumers start parsing/indexing
    try:
        _publish_file_processing_event(file_md5=file_md5, file_name=file_name, file_path=final_path)
        logger.info(f"✅ Merge completed and processing event published for file {file_md5}")
    except Exception as e:
        # Log the error but do not fail the merge; manual trigger endpoint can requeue
        logger.error(f"Failed to publish file processing event for {file_md5}: {e}", exc_info=True)

    return {
        "object_url": final_path,
        "file_size": len(merged_bytes)
    }