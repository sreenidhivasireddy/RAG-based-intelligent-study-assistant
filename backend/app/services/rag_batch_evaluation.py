import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.clients.azure_search import get_azure_search_client
from app.clients.gpt_client import GPTClient
from app.schemas.evaluation import (
    RagBatchDatasetItem,
    RagBatchEvaluationResponse,
    RagBatchResultItem,
)
from app.services.search import HybridSearchService
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _extract_score(row: Dict[str, Any], metric_name: str) -> float:
    exact_candidates = [
        f"{metric_name}.score",
        f"{metric_name}.{metric_name}",
        f"{metric_name}_score",
        f"gpt_{metric_name}",
        f"outputs.{metric_name}.score",
        f"outputs.{metric_name}.{metric_name}",
        f"outputs.{metric_name}_score",
        f"outputs.{metric_name}.gpt_{metric_name}",
        metric_name,
    ]
    for key in exact_candidates:
        if key in row and isinstance(row[key], (float, int)):
            return float(row[key])

    # fallback scan
    for key, value in row.items():
        k = str(key).lower()
        if metric_name in k and isinstance(value, (float, int)):
            if any(
                skip in k
                for skip in ["threshold", "tokens", "finish_reason", "model", "sample_input", "sample_output"]
            ):
                continue
            return float(value)
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                nk = str(nested_key).lower()
                if metric_name in nk and isinstance(nested_value, (float, int)):
                    if any(
                        skip in nk
                        for skip in ["threshold", "tokens", "finish_reason", "model", "sample_input", "sample_output"]
                    ):
                        continue
                    return float(nested_value)

    return 0.0


def _build_context(chunks: List[str], max_chunks: int = 6, max_chars: int = 6000) -> str:
    lines: List[str] = []
    total = 0
    for i, chunk in enumerate(chunks[:max_chunks], 1):
        text = (chunk or "").strip()
        if not text:
            continue
        part = f"[{i}] {text}"
        if total + len(part) > max_chars:
            remaining = max(0, max_chars - total)
            if remaining <= 0:
                break
            part = part[:remaining]
        lines.append(part)
        total += len(part)
        if total >= max_chars:
            break
    return "\n\n".join(lines)


def _score_with_azure_ai_evaluation(rows: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    try:
        from azure.ai.evaluation import evaluate, GroundednessEvaluator, RelevanceEvaluator  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Azure AI Evaluation SDK not available. Install `azure-ai-evaluation`."
        ) from e

    # Faithfulness evaluator availability varies by SDK version.
    faithfulness_cls = None
    try:
        from azure.ai.evaluation import FaithfulnessEvaluator  # type: ignore
        faithfulness_cls = FaithfulnessEvaluator
    except Exception:
        # No strict fallback to heuristic; still use Azure judge evaluator class if Faithfulness isn't shipped.
        faithfulness_cls = GroundednessEvaluator

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

    if not endpoint or not api_key or not deployment:
        raise RuntimeError(
            "Missing Azure OpenAI env vars for evaluation: "
            "AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_CHAT_DEPLOYMENT."
        )

    model_config = {
        "azure_endpoint": endpoint,
        "api_key": api_key,
        "azure_deployment": deployment,
        "api_version": api_version,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        data_path = f.name
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    try:
        evaluators = {
            "groundedness": GroundednessEvaluator(model_config),
            "relevance": RelevanceEvaluator(model_config),
            "faithfulness": faithfulness_cls(model_config),
        }

        evaluator_config = {
            "groundedness": {
                "column_mapping": {
                    "query": "${data.question}",
                    "response": "${data.answer}",
                    "context": "${data.context}",
                }
            },
            "relevance": {
                "column_mapping": {
                    "query": "${data.question}",
                    "response": "${data.answer}",
                    "context": "${data.context}",
                }
            },
            "faithfulness": {
                "column_mapping": {
                    "query": "${data.question}",
                    "response": "${data.answer}",
                    "context": "${data.context}",
                }
            },
        }

        eval_result = evaluate(
            data=data_path,
            evaluators=evaluators,
            evaluator_config=evaluator_config,
        )
        eval_rows = eval_result.get("rows", []) if isinstance(eval_result, dict) else []
        if not eval_rows:
            raise RuntimeError("Azure AI Evaluation returned no rows.")

        scores: List[Dict[str, float]] = []
        missing_score_rows = 0
        for row in eval_rows:
            g_raw = _extract_score(row, "groundedness")
            r_raw = _extract_score(row, "relevance")
            f_raw = _extract_score(row, "faithfulness")
            if g_raw == 0.0 and r_raw == 0.0 and f_raw == 0.0:
                missing_score_rows += 1
            g = max(0.0, min(5.0, g_raw))
            r = max(0.0, min(5.0, r_raw))
            fth = max(0.0, min(5.0, f_raw))
            overall = round(0.4 * g + 0.3 * r + 0.3 * fth, 4)
            scores.append(
                {
                    "groundedness": round(g, 4),
                    "relevance": round(r, 4),
                    "faithfulness": round(fth, 4),
                    "overall_score": overall,
                }
            )
        if missing_score_rows == len(eval_rows):
            raise RuntimeError(
                "Azure AI Evaluation returned rows without groundedness/relevance/faithfulness score fields. "
                "Check evaluator column mapping and Azure model/deployment compatibility."
            )
        return scores
    finally:
        try:
            os.remove(data_path)
        except Exception:
            pass


def run_batch_rag_evaluation(
    dataset: List[RagBatchDatasetItem],
    top_k: int = 5,
    file_md5_filter: Optional[str] = None,
) -> RagBatchEvaluationResponse:
    search_client = get_azure_search_client()
    embedding_client = AzureOpenAIEmbeddingClient()
    search_service = HybridSearchService(search_client=search_client, embedding_client=embedding_client)
    gpt_client = GPTClient()

    run_rows: List[Dict[str, Any]] = []
    base_results: List[RagBatchResultItem] = []

    for item in dataset:
        try:
            search_results, _ = search_service.hybrid_search(
                query=item.question,
                top_k=top_k,
                file_md5_filter=file_md5_filter,
            )
            chunks = [str(r.get("content", "")).strip() for r in search_results if str(r.get("content", "")).strip()]
            context_text = _build_context(chunks)
            if not context_text:
                raise RuntimeError("No retrieved chunks found for this question.")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "Answer the question using only the provided retrieved chunks. "
                        "If insufficient evidence exists, say so explicitly."
                    ),
                },
                {"role": "system", "content": f"Retrieved chunks:\n{context_text}"},
                {"role": "user", "content": item.question},
            ]
            generated_answer = gpt_client.generate(messages)

            run_rows.append(
                {
                    "question": item.question,
                    "answer": generated_answer,
                    "context": context_text,
                    "ground_truth": item.reference_answer or "",
                }
            )
            base_results.append(
                RagBatchResultItem(
                    id=item.id,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    generated_answer=generated_answer,
                    retrieved_chunks=chunks,
                    groundedness=0.0,
                    relevance=0.0,
                    faithfulness=0.0,
                    overall_score=0.0,
                    status="ok",
                )
            )
        except Exception as e:
            base_results.append(
                RagBatchResultItem(
                    id=item.id,
                    question=item.question,
                    reference_answer=item.reference_answer,
                    generated_answer="",
                    retrieved_chunks=[],
                    groundedness=0.0,
                    relevance=0.0,
                    faithfulness=0.0,
                    overall_score=0.0,
                    status="error",
                    error=str(e),
                )
            )

    ok_indices = [i for i, r in enumerate(base_results) if r.status == "ok"]
    eval_rows = [run_rows[i2] for i2 in range(len(run_rows))]

    if eval_rows:
        metric_rows = _score_with_azure_ai_evaluation(eval_rows)
        if len(metric_rows) != len(eval_rows):
            raise RuntimeError("Evaluation row count mismatch.")
        for idx, metric in zip(ok_indices, metric_rows):
            base_results[idx].groundedness = metric["groundedness"]
            base_results[idx].relevance = metric["relevance"]
            base_results[idx].faithfulness = metric["faithfulness"]
            base_results[idx].overall_score = metric["overall_score"]

    succeeded = sum(1 for r in base_results if r.status == "ok")
    failed = len(base_results) - succeeded
    if succeeded > 0:
        avg_grounded = round(sum(r.groundedness for r in base_results if r.status == "ok") / succeeded, 4)
        avg_relevance = round(sum(r.relevance for r in base_results if r.status == "ok") / succeeded, 4)
        avg_faithfulness = round(sum(r.faithfulness for r in base_results if r.status == "ok") / succeeded, 4)
        avg_overall = round(sum(r.overall_score for r in base_results if r.status == "ok") / succeeded, 4)
    else:
        avg_grounded = avg_relevance = avg_faithfulness = avg_overall = 0.0

    return RagBatchEvaluationResponse(
        provider_used="azure_ai_evaluation",
        total_questions=len(base_results),
        succeeded=succeeded,
        failed=failed,
        average_scores={
            "groundedness": avg_grounded,
            "relevance": avg_relevance,
            "faithfulness": avg_faithfulness,
            "overall_score": avg_overall,
        },
        results=base_results,
        evaluated_at=datetime.now(timezone.utc),
    )
