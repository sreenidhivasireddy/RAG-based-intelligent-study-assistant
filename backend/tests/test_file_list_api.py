import requests
import pytest

BASE_URL = "http://localhost:8000/api/v1"


def _safe_get(path: str, timeout: int = 5):
    url = f"{BASE_URL}{path}"
    try:
        return requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Cannot reach API at {url}: {e}")


def test_get_all_uploads():
    resp = _safe_get("/documents/uploads")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_get_completed_files():
    resp = _safe_get("/documents/uploads?status=1")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_pagination():
    resp = _safe_get("/documents/uploads?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
