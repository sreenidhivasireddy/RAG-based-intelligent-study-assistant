"""
Upload-related Data Transfer Objects (DTOs).
Pydantic models for validating and serializing file upload API requests/responses.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from datetime import datetime


class InitiateUploadRequest(BaseModel):
    """Request to initiate a file upload session."""
    file_md5: str = Field(..., min_length=32, max_length=32, description="MD5 hash of the complete file")
    file_name: str = Field(..., min_length=1, max_length=255, description="Original filename")
    total_size: int = Field(..., gt=0, description="Total file size in bytes")
    total_chunks: int = Field(..., gt=0, description="Total number of chunks")
    
    @field_validator('file_md5')
    @classmethod
    def validate_md5(cls, v: str) -> str:
        """Ensure MD5 is alphanumeric and lowercase."""
        if not v.isalnum():
            raise ValueError('MD5 must be alphanumeric')
        return v.lower()
    
    @field_validator('file_name')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Prevent path traversal attacks."""
        if '..' in v or '/' in v or '\\' in v or v.startswith('.'):
            raise ValueError('Filename cannot contain path separators or relative paths')
        if len(v.strip()) == 0:
            raise ValueError('Filename cannot be empty')
        return v.strip()


class InitiateUploadResponse(BaseModel):
    """Response after initiating upload."""
    file_md5: str
    status: str = Field(..., description="Upload session status")
    message: str


class ChunkUploadRequest(BaseModel):
    """Request to upload a single chunk."""
    file_md5: str = Field(..., min_length=32, max_length=32, description="MD5 hash of the complete file")
    chunk_index: int = Field(..., ge=0, description="Index of this chunk (0-based)")
    total_chunks: int = Field(..., gt=0, description="Total number of chunks")
    file_name: str = Field(..., min_length=1, max_length=255, description="Original filename")
    total_size: int = Field(..., gt=0, description="Total file size in bytes")
    
    @field_validator('file_md5')
    @classmethod
    def validate_md5(cls, v: str) -> str:
        """Ensure MD5 is alphanumeric and lowercase."""
        if not v.isalnum():
            raise ValueError('MD5 must be alphanumeric')
        return v.lower()
    
    @field_validator('chunk_index', mode='after')
    @classmethod
    def validate_chunk_index(cls, v: int, info) -> int:
        """Ensure chunk_index is within valid range."""
        total_chunks = info.data.get('total_chunks', 0)
        if total_chunks > 0 and v >= total_chunks:
            raise ValueError(f'chunk_index must be less than total_chunks ({total_chunks})')
        return v
    
    @field_validator('file_name')
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Prevent path traversal attacks."""
        if '..' in v or '/' in v or '\\' in v or v.startswith('.'):
            raise ValueError('Filename cannot contain path separators or relative paths')
        if len(v.strip()) == 0:
            raise ValueError('Filename cannot be empty')
        return v.strip()


class ChunkUploadResponse(BaseModel):
    """Response after uploading a chunk."""
    success: bool
    message: str
    chunk_index: int = Field(..., ge=0)
    progress: float = Field(..., ge=0, le=100, description="Upload progress percentage")
    uploaded_chunks: list[int] = Field(default_factory=list, description="List of uploaded chunk indices")


class CompleteUploadRequest(BaseModel):
    """Request to mark upload as complete and merge chunks."""
    file_md5: str = Field(..., min_length=32, max_length=32)
    total_chunks: int = Field(..., gt=0)
    
    @field_validator('file_md5')
    @classmethod
    def validate_md5(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError('MD5 must be alphanumeric')
        return v.lower()


class CompleteUploadResponse(BaseModel):
    """Response after completing upload."""
    success: bool
    message: str
    file_md5: str
    final_path: Optional[str] = None


class FileUploadStatusResponse(BaseModel):
    """Response for querying file upload status."""
    model_config = ConfigDict(from_attributes=True)
    
    file_md5: str
    file_name: str
    total_size: int
    status: int = Field(..., description="0=uploading, 1=completed")
    progress: float = Field(..., ge=0, le=100)
    uploaded_chunks: list[int] = Field(default_factory=list)
    total_chunks: int
    created_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None


class ChunkInfoResponse(BaseModel):
    """Response model for chunk information."""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    file_md5: str
    chunk_index: int
    chunk_md5: str
    storage_path: str
