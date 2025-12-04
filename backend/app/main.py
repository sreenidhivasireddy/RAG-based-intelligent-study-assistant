# Corresponds to SmartPaiApplication.java

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.upload import router as upload_router
from app.api.documents import router as documents_router
from app.clients import es_index_initializer

logger = logging.getLogger(__name__)

app = FastAPI(
    title="PaiSmart API",
    description="PaiSmart Backend API",
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