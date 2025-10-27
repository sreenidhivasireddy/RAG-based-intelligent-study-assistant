"""
MinIO connection test
Tests MinIO connectivity and basic file operations
"""
import os
import sys
import logging
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load .env from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded .env from: {env_path}")
else:
    logger.warning(f".env not found at: {env_path}")

# Get MinIO configuration from environment
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "False").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "documents")

try:
    # Create MinIO client
    logger.info(f"Testing MinIO connection: {MINIO_ENDPOINT}")
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )
    
    # Check bucket exists or create it
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        logger.info(f"✅ Created bucket: {MINIO_BUCKET}")
    else:
        logger.info(f"✅ Bucket exists: {MINIO_BUCKET}")
    
    # Create temporary directory for test files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create test file
        test_file = tmpdir_path / "test_minio.txt"
        test_content = "Hello from FastAPI & MinIO! Test file."
        test_file.write_text(test_content)
        logger.info(f"Created test file: {test_file}")
        
        # Upload test file
        object_name = "test/test_minio.txt"
        client.fput_object(MINIO_BUCKET, object_name, str(test_file))
        logger.info(f"✅ File uploaded successfully: {object_name}")
        
        # Download and verify
        downloaded_file = tmpdir_path / "downloaded_test.txt"
        client.fget_object(MINIO_BUCKET, object_name, str(downloaded_file))
        downloaded_content = downloaded_file.read_text()
        
        assert downloaded_content == test_content, "File content mismatch!"
        logger.info("✅ File downloaded and verified successfully")
        
        # Cleanup - remove test object
        client.remove_object(MINIO_BUCKET, object_name)
        logger.info(f"✅ Cleaned up test object: {object_name}")
    
    logger.info("✅ MinIO connection test completed successfully")

except S3Error as e:
    logger.error(f"❌ MinIO S3 error: {e}")
    logger.error(f"   Make sure MinIO is running on {MINIO_ENDPOINT}")
    logger.error(f"   Start MinIO: minio server /data --console-address ':9001'")
    sys.exit(1)
except ConnectionError as e:
    logger.error(f"❌ MinIO connection failed: {e}")
    logger.error(f"   Make sure MinIO is running on {MINIO_ENDPOINT}")
    sys.exit(1)
except Exception as e:
    logger.error(f"❌ MinIO test failed: {e}")
    sys.exit(1)
