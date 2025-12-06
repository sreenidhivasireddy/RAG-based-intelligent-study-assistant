# Corresponds to SmartPaiApplication.java

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.upload import router as upload_router
from app.api.documents import router as documents_router
from app.api.search import router as search_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.clients import es_index_initializer

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


@app.on_event("startup")
async def init_elasticsearch():
    """
    Ensure the ES index exists before serving requests.
    """
    try:
        es_index_initializer.ensure_index()
    except Exception as exc:
        logger.warning("Elasticsearch index initialization failed: %s", exc)

@app.get("/")
async def root():
    return {"message": "Welcome to PaiSmart API"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0"
    }