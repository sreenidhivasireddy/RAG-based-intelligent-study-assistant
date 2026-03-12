from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


EvalProvider = Literal["auto", "heuristic", "ragas", "azure_ai_evaluation"]
DatasetSource = Literal["fixed", "synthetic", "both"]
QuestionDifficulty = Literal["easy", "medium", "hard"]


class RagEvaluationRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    retrieved_chunks: List[str] = Field(..., min_length=1)
    reference_answer: Optional[str] = None
    provider: EvalProvider = "auto"
    metadata: Optional[Dict[str, str]] = None


class MetricScore(BaseModel):
    score: float = Field(..., ge=0.0, le=5.0)
    reasoning: str


class RagEvaluationResponse(BaseModel):
    provider_requested: EvalProvider
    provider_used: Literal["heuristic", "ragas", "azure_ai_evaluation"]
    fallback_used: bool = False
    metrics: Dict[str, MetricScore]
    overall_score: float = Field(..., ge=0.0, le=5.0)
    evaluated_at: datetime


class RagBatchDatasetItem(BaseModel):
    id: Optional[str] = None
    question: str = Field(..., min_length=1)
    reference_answer: Optional[str] = None
    context: Optional[List[str]] = None


class RagBatchEvaluationRequest(BaseModel):
    dataset: List[RagBatchDatasetItem] = Field(..., min_length=1)
    provider: Literal["azure_ai_evaluation"] = "azure_ai_evaluation"
    top_k: int = Field(default=5, ge=1, le=20)
    file_md5_filter: Optional[str] = None


class EvaluationRunRequest(BaseModel):
    mode: Optional[DatasetSource] = None
    dataset_source: Optional[DatasetSource] = None

    @model_validator(mode="after")
    def normalize_source(self) -> "EvaluationRunRequest":
        resolved = self.mode or self.dataset_source or "synthetic"
        self.mode = resolved
        self.dataset_source = resolved
        return self


class RagBatchResultItem(BaseModel):
    id: Optional[str] = None
    question: str
    reference_answer: Optional[str] = None
    generated_answer: str
    retrieved_chunks: List[str]
    groundedness: float = Field(..., ge=0.0, le=5.0)
    relevance: float = Field(..., ge=0.0, le=5.0)
    faithfulness: float = Field(..., ge=0.0, le=5.0)
    overall_score: float = Field(..., ge=0.0, le=5.0)
    status: Literal["ok", "error"] = "ok"
    error: Optional[str] = None


class RagBatchEvaluationResponse(BaseModel):
    provider_used: Literal["azure_ai_evaluation"]
    total_questions: int
    succeeded: int
    failed: int
    average_scores: Dict[str, float]
    results: List[RagBatchResultItem]
    evaluated_at: datetime


class FixedQuestion(BaseModel):
    id: str
    question: str
    expected_answer: str
    topic: str
    difficulty: QuestionDifficulty


class EvaluationResult(BaseModel):
    id: Optional[str] = None
    question: str
    expected_answer: Optional[str] = None
    generated_answer: str
    retrieved_chunks: List[str]
    groundedness: float = Field(..., ge=0.0, le=5.0)
    relevance: float = Field(..., ge=0.0, le=5.0)
    similarity: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    overall_score: float = Field(..., ge=0.0, le=5.0)
    status: Literal["ok", "error"] = "ok"
    error: Optional[str] = None
    source: Literal["fixed", "synthetic"]
    topic: Optional[str] = None
    difficulty: Optional[QuestionDifficulty] = None


class EvaluationSummary(BaseModel):
    source: DatasetSource | Literal["overall"]
    total: int
    ok: int
    failed: int
    avg_groundedness: float = Field(..., ge=0.0, le=5.0)
    avg_relevance: float = Field(..., ge=0.0, le=5.0)
    avg_overall: float = Field(..., ge=0.0, le=5.0)
    avg_similarity: Optional[float] = Field(default=None, ge=0.0, le=5.0)


class EvaluationRegressionPoint(BaseModel):
    run_id: str
    run_label: str
    timestamp: datetime
    dataset_source: DatasetSource
    avg_groundedness: float = Field(..., ge=0.0, le=5.0)
    avg_relevance: float = Field(..., ge=0.0, le=5.0)
    avg_overall: float = Field(..., ge=0.0, le=5.0)
    avg_similarity: Optional[float] = Field(default=None, ge=0.0, le=5.0)


class EvaluationRegressionHistory(BaseModel):
    fixed: List[EvaluationRegressionPoint] = Field(default_factory=list)
    synthetic: List[EvaluationRegressionPoint] = Field(default_factory=list)


class AutomatedEvalResponse(BaseModel):
    run_id: str
    mode: DatasetSource
    dataset_source: DatasetSource
    provider_used: Literal["azure_ai_evaluation"]
    summary: EvaluationSummary
    summaries: List[EvaluationSummary]
    results: List[EvaluationResult]
    regression_history: EvaluationRegressionHistory
    evaluated_at: datetime


class SyntheticEvalDatasetItem(BaseModel):
    id: str
    document_id: str
    chunk_id: str
    question: str
    answer: str
    created_at: datetime
    used_in_eval: bool
    pipeline_version: Optional[str] = None


class SyntheticEvalDatasetListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[SyntheticEvalDatasetItem]


class SyntheticEvalCoverageStats(BaseModel):
    documents_with_questions: int
    used_in_eval: int
    unused: int
    avg_questions_per_document: float


class SyntheticEvalStatsResponse(BaseModel):
    total_questions: int
    questions_per_document: Dict[str, int]
    coverage: SyntheticEvalCoverageStats


class SyntheticEvalRegenerateResponse(BaseModel):
    document_id: str
    deleted_old_rows: int
    generated_rows: int
