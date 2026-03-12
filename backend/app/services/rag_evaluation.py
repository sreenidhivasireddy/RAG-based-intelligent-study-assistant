import re
from datetime import datetime, timezone
from typing import Dict, List, Literal, Tuple

from app.schemas.evaluation import MetricScore, RagEvaluationRequest, RagEvaluationResponse


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _f1(a_tokens: List[str], b_tokens: List[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    a_set = set(a_tokens)
    b_set = set(b_tokens)
    overlap = len(a_set & b_set)
    precision = _safe_div(overlap, len(a_set))
    recall = _safe_div(overlap, len(b_set))
    return _safe_div(2 * precision * recall, precision + recall)


def _heuristic_eval(request: RagEvaluationRequest) -> Tuple[Dict[str, MetricScore], float]:
    question_tokens = _tokenize(request.question)
    answer_tokens = _tokenize(request.answer)
    context_text = " ".join((c or "").strip() for c in request.retrieved_chunks if (c or "").strip())
    context_tokens = _tokenize(context_text)

    # Relevance: question-answer lexical semantic overlap proxy.
    relevance_score = _f1(question_tokens, answer_tokens)
    relevance_reason = (
        "Computed from overlap between question and answer key terms "
        f"(question_tokens={len(set(question_tokens))}, answer_tokens={len(set(answer_tokens))})."
    )

    # Groundedness: how much answer is supported by retrieved context.
    answer_unique = set(answer_tokens)
    context_unique = set(context_tokens)
    grounded_overlap = len(answer_unique & context_unique)
    groundedness_score = _safe_div(grounded_overlap, len(answer_unique)) if answer_unique else 0.0
    groundedness_reason = (
        "Estimated by answer-term support in retrieved chunks "
        f"(supported_terms={grounded_overlap}, answer_terms={len(answer_unique)})."
    )

    # Faithfulness: groundedness penalized by unsupported numeric/entity-like terms.
    numerics_in_answer = set(re.findall(r"\b\d+(?:\.\d+)?\b", request.answer or ""))
    numerics_in_context = set(re.findall(r"\b\d+(?:\.\d+)?\b", context_text))
    unsupported_numeric = len(numerics_in_answer - numerics_in_context)
    numeric_penalty = min(0.35, unsupported_numeric * 0.08)
    faithfulness_score = max(0.0, groundedness_score - numeric_penalty)
    faithfulness_reason = (
        "Derived from groundedness with penalty for unsupported numeric claims "
        f"(unsupported_numeric={unsupported_numeric}, penalty={numeric_penalty:.2f})."
    )

    metrics = {
        "groundedness": MetricScore(score=round(groundedness_score, 4), reasoning=groundedness_reason),
        "relevance": MetricScore(score=round(relevance_score, 4), reasoning=relevance_reason),
        "faithfulness": MetricScore(score=round(faithfulness_score, 4), reasoning=faithfulness_reason),
    }
    overall = round(
        0.4 * metrics["groundedness"].score
        + 0.3 * metrics["relevance"].score
        + 0.3 * metrics["faithfulness"].score,
        4,
    )
    return metrics, overall


def _ragas_eval(request: RagEvaluationRequest) -> Tuple[Dict[str, MetricScore], float]:
    """
    Optional RAGAS integration.
    Falls back to heuristic if runtime dependencies are not available.
    """
    # Lightweight stub with graceful failure to keep deployment safe.
    # Full RAGAS integration can be wired when datasets/evaluator dependencies are installed.
    raise RuntimeError("RAGAS runtime dependencies are not installed in this environment.")


def _azure_eval(request: RagEvaluationRequest) -> Tuple[Dict[str, MetricScore], float]:
    """
    Optional Azure AI Evaluation integration.
    Falls back to heuristic if runtime dependencies are not available.
    """
    raise RuntimeError("Azure AI Evaluation runtime dependencies are not installed in this environment.")


def evaluate_rag(request: RagEvaluationRequest) -> RagEvaluationResponse:
    requested = request.provider
    fallback_used = False

    def _build_response(provider_used: Literal["heuristic", "ragas", "azure_ai_evaluation"], metrics, overall):
        return RagEvaluationResponse(
            provider_requested=requested,
            provider_used=provider_used,
            fallback_used=fallback_used,
            metrics=metrics,
            overall_score=overall,
            evaluated_at=datetime.now(timezone.utc),
        )

    if requested == "heuristic":
        metrics, overall = _heuristic_eval(request)
        return _build_response("heuristic", metrics, overall)

    if requested == "ragas":
        try:
            metrics, overall = _ragas_eval(request)
            return _build_response("ragas", metrics, overall)
        except Exception:
            fallback_used = True
            metrics, overall = _heuristic_eval(request)
            return _build_response("heuristic", metrics, overall)

    if requested == "azure_ai_evaluation":
        try:
            metrics, overall = _azure_eval(request)
            return _build_response("azure_ai_evaluation", metrics, overall)
        except Exception:
            fallback_used = True
            metrics, overall = _heuristic_eval(request)
            return _build_response("heuristic", metrics, overall)

    # auto: prefer external provider if available; fallback to heuristic.
    try:
        metrics, overall = _ragas_eval(request)
        return _build_response("ragas", metrics, overall)
    except Exception:
        try:
            metrics, overall = _azure_eval(request)
            return _build_response("azure_ai_evaluation", metrics, overall)
        except Exception:
            fallback_used = True
            metrics, overall = _heuristic_eval(request)
            return _build_response("heuristic", metrics, overall)
