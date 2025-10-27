"""Test minimal upload module."""
from fastapi import APIRouter

from app.utils.logging import get_logger

# Initialize logger
logger = get_logger(__name__)

logger.debug("Creating router...")
router = APIRouter(prefix="/upload", tags=["upload"])
logger.debug(f"Router created: {router}")
