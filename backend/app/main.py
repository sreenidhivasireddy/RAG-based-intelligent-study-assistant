# Corresponds to SmartPaiApplication.java
from pathlib import Path
import os
from dotenv import load_dotenv

# Load backend/.env explicitly
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=True)

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.upload import router as upload_router
from app.api.documents import router as documents_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.quiz import router as quiz_router
from app.api.evaluation import router as evaluation_router
from app.api.evaluate import router as evaluate_router
from app.api.synthetic_eval_dataset import router as synthetic_eval_dataset_router
from app.clients import search_index_initializer
from app.database import ensure_tables



logger = logging.getLogger(__name__)

app = FastAPI(
    title="PaiSmart API",
    description="PaiSmart Backend API with Hybrid Search",
    version="1.0.0"
)

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(conversation_router, prefix="/api/v1/conversations", tags=["conversations"])
app.include_router(quiz_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(evaluate_router, prefix="/api/v1")
app.include_router(synthetic_eval_dataset_router, prefix="/api/v1")


@app.on_event("startup")
async def init_azure_search():
    """
    Ensure database tables and Azure AI Search index configuration are valid before serving requests.
    """
    try:
        ensure_tables()
    except Exception as exc:
        logger.warning("Database table initialization failed: %s", exc)
    try:
        search_index_initializer.ensure_index()
    except Exception as exc:
        logger.warning("Azure AI Search index initialization failed: %s", exc)

@app.get("/")
async def root():
    return {"message": "Welcome to PaiSmart API"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "pipeline_version": os.getenv("PIPELINE_VERSION", "v1.0")
    }
