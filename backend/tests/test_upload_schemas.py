"""
Quick test script to verify upload schemas work correctly.

python tests/test_upload_schemas.py
"""

from app.schemas.upload import (
    ChunkUploadRequest,
    ChunkUploadResponse,
    FileUploadStatusResponse,
)
from pydantic import ValidationError
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_chunk_upload_request():
    """Test ChunkUploadRequest validation."""
    logger.info("\n=== Testing ChunkUploadRequest ===")
    
    # Test valid request
    try:
        req = ChunkUploadRequest(
            file_md5='a' * 32,
            chunk_index=0,
            total_chunks=10,
            file_name='test.pdf',
            total_size=1024000
        )
        logger.info(f'Valid request created: {req.file_md5[:8]}..., chunk {req.chunk_index}/{req.total_chunks}')
    except ValidationError as e:
        logger.error(f'Validation failed: {e}')
    
    # Test invalid MD5 (too short)
    try:
        req = ChunkUploadRequest(
            file_md5='abc123',
            chunk_index=0,
            total_chunks=10,
            file_name='test.pdf',
            total_size=1024000
        )
        logger.error('Should have rejected invalid MD5')
    except ValidationError:
        logger.info('Correctly rejected invalid MD5 (too short)')
    
    # Test invalid chunk_index (negative)
    try:
        req = ChunkUploadRequest(
            file_md5='a' * 32,
            chunk_index=-1,
            total_chunks=10,
            file_name='test.pdf',
            total_size=1024000
        )
        logger.error('Should have rejected negative chunk_index')
    except ValidationError:
        logger.info('Correctly rejected negative chunk_index')
    
    # Test path traversal protection
    try:
        req = ChunkUploadRequest(
            file_md5='a' * 32,
            chunk_index=0,
            total_chunks=10,
            file_name='../../etc/passwd',
            total_size=1024000
        )
        logger.error('Should have rejected path traversal')
    except ValidationError:
        logger.info('Correctly rejected path traversal in filename')


def test_chunk_upload_response():
    """Test ChunkUploadResponse creation."""
    logger.info("\n=== Testing ChunkUploadResponse ===")
    
    response = ChunkUploadResponse(
        success=True,
        message="Chunk 0 uploaded successfully",
        chunk_index=0,
        progress=10.0,
        uploaded_chunks=[0]
    )
    logger.info(f'Response created: {response.message}, progress={response.progress}%')
    logger.info(f'   Uploaded chunks: {response.uploaded_chunks}')


def test_file_status_response():
    """Test FileUploadStatusResponse."""
    logger.info("\n=== Testing FileUploadStatusResponse ===")
    
    status = FileUploadStatusResponse(
        file_md5='a' * 32,
        file_name='document.pdf',
        total_size=1024000,
        status=0,
        progress=25.5,
        uploaded_chunks=[0, 1, 2],
        total_chunks=10
    )
    logger.info(f'Status response created: {status.file_name}')
    logger.info(f'   Progress: {status.progress}%, Status: {status.status}')
    logger.info(f'   Uploaded: {len(status.uploaded_chunks)}/{status.total_chunks} chunks')


if __name__ == '__main__':
    logger.info("🧪 Testing Upload Schemas...")
    test_chunk_upload_request()
    test_chunk_upload_response()
    test_file_status_response()
    logger.info("\n🎉 All schema tests passed!")
