"""
Azure Blob Storage client for file upload and management.
Replaces MinIO with Azure Blob Storage for cloud-native object storage.

This module provides drop-in replacement functions with identical signatures
to the previous MinIO implementation, ensuring backward compatibility.
"""

import os
from pathlib import Path
from typing import Optional
from azure.storage.blob import BlobServiceClient, ContainerClient, BlobProperties, ContentSettings
from azure.core.exceptions import AzureError, ResourceExistsError
from dotenv import load_dotenv
from nltk import data

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Configuration from environment variables
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "documents")


class AzureBlobStorageClient:
    """
    Azure Blob Storage client compatible with MinIO operations.
    Provides functions with identical signatures to MinIO usage.
    """
    
    def __init__(
        self,
        connection_string: str = None,
        container_name: str = None
    ):
        """
        Initialize Azure Blob Storage client.
        
        Args:
            connection_string: Azure Storage connection string
                              (defaults to AZURE_STORAGE_CONNECTION_STRING env var)
            container_name: Container name (defaults to AZURE_STORAGE_CONTAINER env var)
        
        Raises:
            ValueError: If connection string is missing
            RuntimeError: If client initialization fails
        """
        self.connection_string = connection_string or AZURE_STORAGE_CONNECTION_STRING
        self.container_name = container_name or AZURE_STORAGE_CONTAINER
        
        if not self.connection_string:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING environment variable is required.\n"
                "Please set it in your .env file or system environment.\n"
                "Format: DefaultEndpointsProtocol=https;AccountName=<name>;AccountKey=<key>;EndpointSuffix=core.windows.net"
            )
        
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            
            # Ensure container exists
            self._ensure_container_exists()
            
            logger.info(
                f"✓ Azure Blob Storage client initialized\n"
                f"  Container: {self.container_name}"
            )
        except Exception as e:
            logger.error(f"✗ Failed to initialize Azure Blob Storage: {e}")
            raise RuntimeError(f"Failed to initialize Azure Blob Storage: {e}") from e
    
    def _ensure_container_exists(self) -> None:
        """
        Ensure the container exists, creating it if necessary.
        Handles the case where container already exists gracefully.
        """
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            # Try to get container properties to check existence
            try:
                container_client.get_container_properties()
                logger.info(f"Container '{self.container_name}' already exists")
            except AzureError:
                # Container doesn't exist, create it
                self.blob_service_client.create_container(name=self.container_name)
                logger.info(f"Created container '{self.container_name}'")
        except ResourceExistsError:
            # Another process created it concurrently
            logger.info(f"Container '{self.container_name}' created by concurrent process")
        except Exception as e:
            logger.error(f"Error checking/creating container: {e}")
            raise
    
    def upload_bytes(
        self,
        data: bytes,
        object_name: str,
        content_type: str = None
    ) -> str:
        """
        Upload bytes to blob storage.
        
        Args:
            data: Binary content to upload
            object_name: Path/name of the blob (e.g., "chunks/abc123/0")
            content_type: MIME type (e.g., "application/octet-stream")
        
        Returns:
            The blob name (object_name) on success
        
        Raises:
            Exception: If upload fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=object_name
            )
            
            upload_options = {}
            if content_type:
                upload_options["content_settings"] = ContentSettings(content_type=content_type)

            blob_client.upload_blob(data, overwrite=True, **upload_options)
            
            
            
            logger.info(
                f"Uploaded blob: {object_name} "
                f"({len(data)} bytes, {self.container_name})"
            )
            return object_name
            
        except Exception as e:
            logger.error(f"Failed to upload blob {object_name}: {e}")
            raise RuntimeError(f"Failed to upload blob {object_name}: {e}") from e
    
    def upload_file(
        self,
        local_path: str,
        object_name: str = None,
        content_type: str = None
    ) -> str:
        """
        Upload a local file to blob storage.
        
        Args:
            local_path: Path to local file
            object_name: Destination blob name (defaults to filename)
            content_type: MIME type
        
        Returns:
            The blob name on success
        
        Raises:
            FileNotFoundError: If local file doesn't exist
            Exception: If upload fails
        """
        local_path = Path(local_path)
        
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        if object_name is None:
            object_name = local_path.name
        
        try:
            with open(local_path, 'rb') as data:
                file_data = data.read()
            
            return self.upload_bytes(file_data, object_name, content_type)
            
        except Exception as e:
            logger.error(f"Failed to upload file {local_path} to {object_name}: {e}")
            raise RuntimeError(
                f"Failed to upload file {local_path} to {object_name}: {e}"
            ) from e
    
    def download_bytes(self, object_name: str) -> bytes:
        """
        Download blob content as bytes.
        
        Args:
            object_name: Path/name of the blob
        
        Returns:
            Binary content of the blob
        
        Raises:
            Exception: If blob doesn't exist or download fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=object_name
            )
            
            download_stream = blob_client.download_blob()
            data = download_stream.readall()
            
            logger.info(f"Downloaded blob: {object_name} ({len(data)} bytes)")
            return data
            
        except Exception as e:
            logger.error(f"Failed to download blob {object_name}: {e}")
            raise RuntimeError(f"Failed to download blob {object_name}: {e}") from e
    
    def download_file(self, object_name: str, local_path: str) -> None:
        """
        Download a blob to a local file.
        
        Args:
            object_name: Path/name of the blob
            local_path: Destination local file path
        
        Raises:
            Exception: If download fails
        """
        try:
            data = self.download_bytes(object_name)
            
            # Create parent directories if needed
            local_path_obj = Path(local_path)
            local_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_path, 'wb') as f:
                f.write(data)
            
            logger.info(f"Downloaded blob to file: {local_path}")
            
        except Exception as e:
            logger.error(f"Failed to download blob {object_name} to {local_path}: {e}")
            raise RuntimeError(
                f"Failed to download blob {object_name} to {local_path}: {e}"
            ) from e
    
    def delete_object(self, object_name: str) -> None:
        """
        Delete a blob from storage.
        
        Args:
            object_name: Path/name of the blob
        
        Raises:
            Exception: If deletion fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=object_name
            )
            
            blob_client.delete_blob()
            logger.info(f"Deleted blob: {object_name}")
            
        except Exception as e:
            logger.error(f"Failed to delete blob {object_name}: {e}")
            raise RuntimeError(f"Failed to delete blob {object_name}: {e}") from e
    
    def list_objects(self, prefix: str = None) -> list[str]:
        """
        List blobs in container with optional prefix filtering.
        
        Args:
            prefix: Optional path prefix to filter blobs (e.g., "documents/")
        
        Returns:
            List of blob names matching the prefix
        
        Raises:
            Exception: If listing fails
        """
        try:
            container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
            
            blobs = container_client.list_blobs(name_starts_with=prefix)
            blob_names = [blob.name for blob in blobs]
            
            logger.info(f"Listed {len(blob_names)} blobs with prefix '{prefix}'")
            return blob_names
            
        except Exception as e:
            logger.error(f"Failed to list blobs with prefix '{prefix}': {e}")
            raise RuntimeError(f"Failed to list blobs: {e}") from e
    
    def stat_object(self, object_name: str) -> dict:
        """
        Get blob metadata/properties (MinIO-compatible).
        
        Args:
            object_name: Path/name of the blob
        
        Returns:
            Dictionary with blob properties
        
        Raises:
            Exception: If blob doesn't exist or query fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=object_name
            )
            
            properties = blob_client.get_blob_properties()
            
            return {
                "name": properties.name,
                "size": properties.size,
                "etag": properties.etag,
                "last_modified": properties.last_modified,
                "content_type": (
                    properties.content_settings.content_type
                    if properties.content_settings
                    else None
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to get properties for blob {object_name}: {e}")
            raise RuntimeError(f"Failed to stat object {object_name}: {e}") from e


# Global singleton instance
_azure_blob_client = None


def get_azure_blob_client() -> AzureBlobStorageClient:
    """
    Get or create the Azure Blob Storage client (singleton pattern).
    
    Returns:
        AzureBlobStorageClient: Initialized client instance
    
    Raises:
        RuntimeError: If client cannot be initialized
    """
    global _azure_blob_client
    
    if _azure_blob_client is not None:
        return _azure_blob_client
    
    try:
        _azure_blob_client = AzureBlobStorageClient(
            connection_string=AZURE_STORAGE_CONNECTION_STRING,
            container_name=AZURE_STORAGE_CONTAINER
        )
        return _azure_blob_client
    except Exception as e:
        logger.error(f"Failed to initialize Azure Blob Storage client: {e}")
        raise


# Initialize on module load with graceful fallback
try:
    azure_blob_client = get_azure_blob_client()
except Exception as e:
    logger.warning(f"Azure Blob Storage initialization deferred: {e}")
    azure_blob_client = None


# Backward compatibility: export with MinIO-like usage pattern
__all__ = [
    'AzureBlobStorageClient',
    'get_azure_blob_client',
    'azure_blob_client',
    'AZURE_STORAGE_CONTAINER',
    'AZURE_STORAGE_CONNECTION_STRING'
]
