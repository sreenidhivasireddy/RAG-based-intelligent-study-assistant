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
from app.schemas.upload import ChunkUploadRequest, FileMergeRequest, FileMergeResponse
from app.services.upload import upload_chunk_service, calculate_upload_progress, merge_file_service
from app.repositories.upload_repository import get_file_upload
from app.clients.kafka import KafkaConfig
from app.models.file_processing_task import FileProcessingTask
from app.utils.logging import get_logger

logger = get_logger(__name__)

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


@router.post("/merge")
def merge_file(
    request: FileMergeRequest,
    db: Session = Depends(get_db)
):
    """
    合并文件并发送到Kafka处理队列
    Merge all uploaded file chunks into a single complete file.
    
    **URL**: `/api/v1/upload/merge`  
    **Method**: `POST`  
    **Content-Type**: `application/json`
    
    **Request Body**:
    ```json
    {
      "file_md5": "d41d8cd98f00b204e9800998ecf8427e",
      "file_name": "annual-report.pdf"
    }
    ```
    
    **Response** (200 OK):
    ```json
    {
      "code": 200,
      "message": "File merged successfully",
      "data": {
        "object_url": "documents/d41d8cd98f00b204e9800998ecf8427e/annual-report.pdf",
        "file_size": 15728640
      }
    }
    ```
    
    **Response** (400 Bad Request - Missing chunks):
    ```json
    {
      "code": 400,
      "message": "Not all chunks have been uploaded. Missing chunks: [2, 5]. Upload progress: 8/10"
    }
    ```
    
    **Response** (400 Bad Request - File not found):
    ```json
    {
      "code": 400,
      "message": "File not found in database. Please upload chunks first."
    }
    ```
    
    **Business Logic Flow**:
    
    1. **Validate file exists** - Check MySQL `file_upload` table for file_md5
       - Ensures this file was previously registered during chunk uploads
       - Returns 400 if not found
    
    2. **Verify all chunks uploaded** - Check Redis bitmap for completion
       - Redis key: `upload:{file_md5}:chunks`
       - Each bit represents one chunk (0=missing, 1=uploaded)
       - Returns 400 with missing chunk list if incomplete
    
    3. **Fetch chunk metadata** - Query MySQL `chunk_info` table
       - Get storage_path for each chunk (e.g., `chunks/{md5}/{index}`)
       - Order by chunk_index to ensure correct concatenation sequence
    
    4. **Download chunks from MinIO** - Retrieve binary data in order
       - Loop through chunks sequentially (chunk0 → chunk1 → chunk2 → ...)
       - Concatenate bytes in memory (suitable for files < 200MB)
       - For larger files, consider streaming to temporary file
    
    5. **Upload merged file to permanent storage** - Store complete file
       - Final path: `documents/{file_md5}/{file_name}`
       - This separates temporary chunks from permanent storage
       - Preserves original filename for proper downloads
    
    6. **Update file status in MySQL** - Mark as completed
       - Set `file_upload.status = 1` (0=uploading, 1=completed)
       - Update `merged_at` timestamp
       - Enables client queries to check if file is ready
    
    7. **Publish Kafka event (optional)** - Trigger downstream processing
       - Send message to parsing topic for PDF text extraction
       - Enables async vector embedding and indexing
       - Decouples upload from processing pipeline
    
    8. **Cleanup temporary chunks (optional)** - Free storage space
       - Can delete chunk files after successful merge
       - Or use background job with TTL policy (recommended)
    
    **Why This Design?**
    
    - **Redis bitmap**: O(1) chunk existence check, fast progress calculation
    - **MySQL chunk_info**: Persistent metadata, enables crash recovery
    - **MinIO separation**: Chunks in `/chunks`, final in `/documents`
    - **Status tracking**: Clients can poll for completion before download
    - **Kafka integration**: Async processing prevents blocking uploads
    
    **Use Cases**:
    - Complete multi-part file upload workflow
    - Reconstruct original file from chunks
    - Trigger downstream parsing/indexing pipeline
    - Enable file download after successful merge
    """
    try:
        # Call service layer to perform merge
        result = merge_file_service(
            db=db,
            file_md5=request.file_md5,
            file_name=request.file_name
        )

        # 2. 创建Kafka任务
        # 对应Java:
        # FileProcessingTask task = new FileProcessingTask(...);
        task = FileProcessingTask(
            file_md5=request.file_md5,
            file_path=result['object_url'],
            file_name=request.file_name
        )
        
         # 3. 发送到Kafka
        # 对应Java:
        # kafkaTemplate.executeInTransaction(kt -> {
        #     kt.send(kafkaConfig.getFileProcessingTopic(), task);
        #     return true;
        # });
        
        try:
            # 获取producer（对应 @Autowired KafkaTemplate）
            producer = KafkaConfig.get_producer()
            
            # 获取topic名称（对应 kafkaConfig.getFileProcessingTopic()）
            topic = KafkaConfig.get_file_processing_topic()
            
            logger.info(
                f"发送任务到Kafka: topic={topic}, "
                f"fileMd5={task.file_md5}, fileName={task.file_name}"
            )
            
            # 发送消息
            future = producer.send(
                topic,
                key=task.file_md5,
                value=task.to_dict()
            )
            
            # 同步等待发送完成（对应Java的事务提交）
            record_metadata = future.get(timeout=10)
            
            logger.info(
                f"任务发送成功: partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}"
            )

        except Exception as kafka_error:
            logger.error(f"Kafka发送失败: {kafka_error}", exc_info=True)
            # 可以选择是否抛出异常
            # 如果文件已合并，Kafka失败可能只记录日志

        # Return success response with file info
        return {
            "code": 200,
            "message": "File merged successfully",
            "data": result
        }
        
    except Exception as e:
        # Handle validation and merge errors
        error_message = str(e)
        
        # Determine appropriate error code
        if "not found" in error_message.lower():
            code = 404
        elif "not all chunks" in error_message.lower() or "missing" in error_message.lower():
            code = 400
        else:
            code = 500
        
        return {
            "code": code,
            "message": error_message
        }

