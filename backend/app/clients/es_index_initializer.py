"""
Elasticsearch index initializer shim.

This is a lightweight compatibility shim used when running tests locally
without a running Elasticsearch cluster. It provides an `ensure_index`
function that logs and returns True. When real ES is available, replace
or extend this module with real initialization logic.
"""

from app.utils.logging import get_logger

logger = get_logger(__name__)


def ensure_index(index_name: str = None) -> bool:
    """No-op ensure index: returns True and logs a warning.

    This allows tests that import `app.clients.es_index_initializer` to
    run in environments where Elasticsearch is not available.
    """
    try:
        logger.warning("es_index_initializer.ensure_index() invoked — running in shim mode (no ES).")
        return True
    except Exception as e:
        logger.error(f"Failed to ensure index: {e}")
        raise


def create_index(*args, **kwargs):
    raise NotImplementedError("ES index creation not implemented in shim")
