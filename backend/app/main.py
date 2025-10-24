 #对应 SmartPaiApplication.java

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import Settings

app = FastAPI(
    title="PaiSmart API",
    description="PaiSmart Backend API",
    version="1.0.0"
)

# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Welcome to PaiSmart API"}