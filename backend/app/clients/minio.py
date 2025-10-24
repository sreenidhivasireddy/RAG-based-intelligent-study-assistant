"""
MinIO client initialization.
Provides a reusable MinIO connection for other modules.
"""

import os
from minio import Minio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true"

try:
    minio_client = Minio(
        endpoint=MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )
    # Ensure the default bucket exists
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)
        print(f"Created bucket: {MINIO_BUCKET}")
    else:
        print(f"MinIO connected ({MINIO_ENDPOINT}) — Bucket: {MINIO_BUCKET}")
except Exception as e:
    print(f"Failed to initialize MinIO client: {e}")
    minio_client = None
