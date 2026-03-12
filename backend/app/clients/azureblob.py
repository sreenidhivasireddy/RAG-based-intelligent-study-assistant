"""
Azure Blob Storage client initialization.
Provides a reusable Blob Storage connection for other modules.
"""

import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

from app.utils.logging import get_logger

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "documents")

try:
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise ValueError(
            "Missing AZURE_STORAGE_CONNECTION_STRING. "
            "Set it in .env (Storage Account -> Access keys -> Connection string)."
        )

    blob_service_client = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    container_client = blob_service_client.get_container_client(AZURE_STORAGE_CONTAINER)

    # Ensure the container exists
    try:
        container_client.create_container()
        logger.info(f"Created Azure Blob container: {AZURE_STORAGE_CONTAINER}")
    except ResourceExistsError:
        logger.info(f"Azure Blob connected — Container: {AZURE_STORAGE_CONTAINER}")

except Exception as e:
    logger.error(f"Failed to initialize Azure Blob client: {e}")
    blob_service_client = None
    container_client = None