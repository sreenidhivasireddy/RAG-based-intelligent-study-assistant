"""
MySQL client initialization module.
Provides a reusable connection pool for database operations.

Usage:
    from app.clients.mysql_client import get_connection

    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM file_upload;")
        rows = cursor.fetchall()
"""

import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "rag")

# Initialize MySQL connection pool
try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="mysql_pool",
        pool_size=5,
        pool_reset_session=True,
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    print(f"✅ MySQL connection pool created successfully ({MYSQL_HOST}:{MYSQL_PORT})")
except Exception as e:
    print(f"❌ Failed to create MySQL connection pool: {e}")
    connection_pool = None


def get_connection():
    """
    Get a connection from the pool.
    Always close the connection after use.
    """
    if not connection_pool:
        raise ConnectionError("MySQL connection pool not initialized.")
    try:
        return connection_pool.get_connection()
    except Exception as e:
        print(f"❌ Error getting MySQL connection: {e}")
        raise
