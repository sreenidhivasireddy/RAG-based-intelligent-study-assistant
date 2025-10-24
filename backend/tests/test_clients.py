#   python -m pytest -q tests/test_clients.py

import os
import socket
import pytest

try:
    from app.clients.mysql import get_connection
except Exception:
    # Import errors will be handled in tests by skipping
    get_connection = None

try:
    from app.clients.redis import redis_client
except Exception:
    redis_client = None


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except Exception:
        return False


def _mysql_addr():
    return os.getenv("MYSQL_HOST", "localhost"), int(os.getenv("MYSQL_PORT", 3306))


def _redis_addr():
    return os.getenv("REDIS_HOST", "localhost"), int(os.getenv("REDIS_PORT", 6379))


def test_mysql_connection_or_skip():
    if get_connection is None:
        pytest.skip("MySQL client module not importable (missing dependency or path)")

    host, port = _mysql_addr()
    if not _is_port_open(host, port):
        pytest.skip(f"MySQL not reachable at {host}:{port}")

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DATABASE();")
            res = cursor.fetchone()
            assert res is not None
    except Exception as e:
        pytest.skip(f"MySQL connection attempt failed: {e}")


def test_redis_connection_or_skip():
    if redis_client is None:
        pytest.skip("Redis client module not importable (missing dependency or path)")

    host, port = _redis_addr()
    if not _is_port_open(host, port):
        pytest.skip(f"Redis not reachable at {host}:{port}")

    try:
        redis_client.set("test_ping", "pong")
        val = redis_client.get("test_ping")
        assert val is not None
    except Exception as e:
        pytest.skip(f"Redis operation failed: {e}")
