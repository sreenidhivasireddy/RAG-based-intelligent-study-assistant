from minio import Minio
from dotenv import load_dotenv
import os

load_dotenv()

# 读取环境变量
client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE", "False").lower() == "true"
)

bucket = os.getenv("MINIO_BUCKET")

# 检查桶是否存在
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)
    print(f"✅ Created bucket: {bucket}")
else:
    print(f"✅ Bucket exists: {bucket}")

# 上传测试文件
with open("test.txt", "w") as f:
    f.write("Hello from FastAPI & MinIO!")

client.fput_object(bucket, "test.txt", "test.txt")
print("✅ File uploaded successfully!")

# 下载验证
client.fget_object(bucket, "test.txt", "downloaded_test.txt")
print("✅ File downloaded successfully!")

print("🎉 MinIO setup is working perfectly!")
