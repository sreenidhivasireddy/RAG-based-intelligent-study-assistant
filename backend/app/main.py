# Corresponds to SmartPaiApplication.java

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.upload import router as upload_router

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

@app.get("/")
async def root():
    return {"message": "Welcome to PaiSmart API"}