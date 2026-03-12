from fastapi import APIRouter, HTTPException

from app.schemas.evaluation import (
    RagBatchEvaluationRequest,
    RagBatchEvaluationResponse,
    RagEvaluationRequest,
    RagEvaluationResponse,
)
from app.services.rag_evaluation import evaluate_rag
from app.services.rag_batch_evaluation import run_batch_rag_evaluation
from app.utils.logging import get_logger


router = APIRouter(prefix="/evaluation", tags=["evaluation"])
logger = get_logger(__name__)


@router.post("/rag", response_model=RagEvaluationResponse)
async def evaluate_rag_answer(request: RagEvaluationRequest):
    try:
        return evaluate_rag(request)
    except Exception as e:
        logger.error("RAG evaluation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG evaluation failed: {str(e)}")


@router.post("/rag/batch", response_model=RagBatchEvaluationResponse)
async def evaluate_rag_batch(request: RagBatchEvaluationRequest):
    try:
        if request.provider != "azure_ai_evaluation":
            raise HTTPException(
                status_code=400,
                detail="Batch evaluation supports provider='azure_ai_evaluation' only.",
            )
        return run_batch_rag_evaluation(
            dataset=request.dataset,
            top_k=request.top_k,
            file_md5_filter=request.file_md5_filter,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Batch RAG evaluation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch RAG evaluation failed: {str(e)}")
