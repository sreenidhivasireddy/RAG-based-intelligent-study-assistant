"""
Azure Blob Storage service for file uploads.
"""

import io
import os
from azure.storage.blob import BlobServiceClient, BlobClient, ContentSettings
from azure.core.exceptions import AzureError
from dotenv import load_dotenv

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# Azure Blob Storage configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "documents")


class AzureBlobStorage:
    """
    Azure Blob Storage client for file operations.
    Provides interface compatible with previous MinIO operations.
    """
    
    def __init__(self, connection_string: str = None, container: str = None):
        """
        Initialize Azure Blob Storage client.
        
        Args:
            connection_string: Azure Storage connection string (defaults to env var)
            container: Container name (defaults to env var)
            
        Raises:
            ValueError: If connection string is missing
        """
        self.connection_string = connection_string or AZURE_STORAGE_CONNECTION_STRING
        self.container = container or AZURE_STORAGE_CONTAINER
        
        if not self.connection_string:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING not configured. "
                "Please set environment variable or pass connection_string parameter."
            )
        
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            
            # Ensure container exists
            self.container_client = self.blob_service_client.get_container_client(self.container)
            try:
                self.container_client.get_container_properties()
                logger.info(f"✓ Azure Blob Storage connected — Container: {self.container}")
            except AzureError:
                # Container doesn't exist, create it
                self.container_client = self.blob_service_client.create_container(self.container)
                logger.info(f"✓ Created Azure Blob Storage container: {self.container}")
                
        except Exception as e:
            logger.error(f"✗ Failed to initialize Azure Blob Storage: {e}")
            raise RuntimeError(f"Failed to initialize Azure Blob Storage: {e}") from e
    
    def upload_bytes(self, blob_name: str, data: bytes, content_type: str = None) -> dict:
        """
        Upload bytes to blob storage.
        
        Args:
            blob_name: Path/name of the blob
            data: Binary content to upload
            content_type: MIME type (e.g., 'application/pdf')
            
        Returns:
            Dict with upload status and metadata
            
        Raises:
            Exception: If upload fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container,
                blob=blob_name
            )
            
            # Upload blob with optional content type
            upload_options = {}
            if content_type:
                upload_options["content_settings"] = ContentSettings(content_type=content_type)

            blob_client.upload_blob(
                data,
                overwrite=True,
                **upload_options
        )
            
            logger.info(f"Uploaded blob: {blob_name} ({len(data)} bytes)")
            return {
                "success": True,
                "blob_name": blob_name,
                "size": len(data),
                "container": self.container
            }
            
        except Exception as e:
            logger.error(f"Failed to upload blob {blob_name}: {e}")
            raise
    
    def download_bytes(self, blob_name: str) -> bytes:
        """
        Download bytes from blob storage.
        
        Args:
            blob_name: Path/name of the blob
            
        Returns:
            Binary content of the blob
            
        Raises:
            Exception: If blob doesn't exist or download fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container,
                blob=blob_name
            )
            
            download_stream = blob_client.download_blob()
            data = download_stream.readall()
            
            logger.info(f"Downloaded blob: {blob_name} ({len(data)} bytes)")
            return data
            
        except Exception as e:
            logger.error(f"Failed to download blob {blob_name}: {e}")
            raise
    
    def delete(self, blob_name: str) -> bool:
        """
        Delete a blob from storage.
        
        Args:
            blob_name: Path/name of the blob
            
        Returns:
            True if deletion succeeded
            
        Raises:
            Exception: If deletion fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container,
                blob=blob_name
            )
            
            blob_client.delete_blob()
            logger.info(f"Deleted blob: {blob_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete blob {blob_name}: {e}")
            raise
    
    def stat_object(self, blob_name: str) -> dict:
        """
        Get blob metadata/properties (compatible with MinIO stat_object).
        
        Args:
            blob_name: Path/name of the blob
            
        Returns:
            Dict with blob properties
            
        Raises:
            Exception: If blob doesn't exist or query fails
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container,
                blob=blob_name
            )
            
            properties = blob_client.get_blob_properties()
            
            return {
                "size": properties.size,
                "etag": properties.etag,
                "last_modified": properties.last_modified,
                "content_type": properties.content_settings.content_type if properties.content_settings else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get properties for blob {blob_name}: {e}")
            raise
    
    def exists(self, blob_name: str) -> bool:
        """
        Check if a blob exists.
        
        Args:
            blob_name: Path/name of the blob
            
        Returns:
            True if blob exists, False otherwise
        """
        try:
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container,
                blob=blob_name
            )
            
            blob_client.get_blob_properties()
            return True
            
        except AzureError:
            return False
        except Exception as e:
            logger.error(f"Error checking blob existence {blob_name}: {e}")
            return False


# Global instance
_blob_storage_client = None


def get_blob_storage_client() -> AzureBlobStorage:
    """
    Get or create the Azure Blob Storage client (singleton pattern).
    
    Returns:
        AzureBlobStorage: Blob storage client instance
        
    Raises:
        RuntimeError: If client cannot be initialized
    """
    global _blob_storage_client
    
    if _blob_storage_client is not None:
        return _blob_storage_client
    
    try:
        _blob_storage_client = AzureBlobStorage(
            connection_string=AZURE_STORAGE_CONNECTION_STRING,
            container=AZURE_STORAGE_CONTAINER
        )
        return _blob_storage_client
    except Exception as e:
        logger.error(f"Failed to initialize blob storage client: {e}")
        raise


# Initialize client on module load
try:
    blob_storage_client = get_blob_storage_client()
except Exception as e:
    logger.warning(f"Blob storage client initialization deferred: {e}")
    blob_storage_client = None
