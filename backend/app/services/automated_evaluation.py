import json
import os
import random
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.clients.azure_search import get_azure_search_client
from app.clients.gpt_client import GPTClient
from app.database import SessionLocal, ensure_tables
from app.repositories.evaluation_run_repository import create_evaluation_run, list_evaluation_runs
from app.repositories.fixed_eval_repository import (
    count_fixed_eval_questions,
    list_fixed_eval_questions,
    seed_fixed_eval_questions_from_file,
)
from app.repositories.synthetic_eval_repository import (
    fetch_synthetic_eval_rows_for_evaluation,
    mark_synthetic_eval_rows_used,
)
from app.schemas.evaluation import (
    AutomatedEvalResponse,
    DatasetSource,
    EvaluationRegressionHistory,
    EvaluationRegressionPoint,
    EvaluationResult,
    EvaluationSummary,
    QuestionDifficulty,
)
from app.services.search import HybridSearchService
from app.services.synthetic_eval_generation import trigger_synthetic_eval_backfill_background
from app.utils.logging import get_logger

logger = get_logger(__name__)

DatasetRow = Dict[str, Any]


def _is_content_filter_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "content_filter" in message or "responsibleaipolicyviolation" in message


def _generate_eval_answer(
    gpt_client: GPTClient,
    question: str,
    context: str,
) -> str:
    primary_messages = [
        {
            "role": "system",
            "content": (
                "Answer using only the retrieved chunks. "
                "Treat the material as academic or cybersecurity research content. "
                "Do not add extra facts. If evidence is insufficient, say so."
            ),
        },
        {"role": "system", "content": f"Retrieved chunks:\n{context}"},
        {"role": "user", "content": question},
    ]
    try:
        return gpt_client.generate(messages=primary_messages)
    except Exception as exc:
        if not _is_content_filter_error(exc):
            raise

        fallback_context = context[:2500]
        fallback_messages = [
            {
                "role": "system",
                "content": (
                    "You are summarizing academic document excerpts for evaluation. "
                    "Some excerpts may discuss cyberattacks or security abuse in a research context. "
                    "Answer neutrally using only the supplied text. If unsure, say the evidence is insufficient."
                ),
            },
            {"role": "system", "content": f"Document excerpts:\n{fallback_context}"},
            {"role": "user", "content": question},
        ]
        logger.warning(
            "Evaluation generation hit Azure content filter. Retrying with safer evaluation prompt for question=%s",
            question[:120],
        )
        return gpt_client.generate(messages=fallback_messages)


def _extract_score(row: Dict[str, Any], metric_name: str) -> Tuple[float, Optional[str]]:
    candidates = [
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
    for key in candidates:
        if key in row and isinstance(row[key], (int, float)):
            return float(row[key]), key

    for key, value in row.items():
        k = str(key).lower()
        if metric_name in k and isinstance(value, (int, float)):
            if any(skip in k for skip in ["threshold", "tokens", "finish_reason", "model", "sample_input", "sample_output"]):
                continue
            return float(value), key
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                nk = str(nested_key).lower()
                if metric_name in nk and isinstance(nested_value, (int, float)):
                    if any(skip in nk for skip in ["threshold", "tokens", "finish_reason", "model", "sample_input", "sample_output"]):
                        continue
                    return float(nested_value), f"{key}.{nested_key}"
    return 0.0, None


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


def _sample_rows(rows: List[DatasetRow], max_rows: int) -> List[DatasetRow]:
    if len(rows) <= max_rows:
        return rows
    return [rows[i] for i in random.sample(range(len(rows)), max_rows)]


def _dedupe_rows_by_question(rows: List[DatasetRow]) -> List[DatasetRow]:
    seen: set[str] = set()
    deduped: List[DatasetRow] = []
    for row in rows:
        key = str(row["question"]).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _load_synthetic_rows(only_unused: bool = True, limit: int = 200) -> List[DatasetRow]:
    db = SessionLocal()
    try:
        rows = fetch_synthetic_eval_rows_for_evaluation(db, limit=limit, only_unused=only_unused)
        return [
            {
                "id": f"synthetic:{row.id}",
                "row_id": row.id,
                "question": row.question,
                "expected_answer": row.answer,
                "context": None,
                "source": "synthetic",
                "topic": None,
                "difficulty": None,
            }
            for row in rows
        ]
    finally:
        db.close()


def _ensure_fixed_dataset_seeded(seed_path: Path) -> None:
    db = SessionLocal()
    try:
        if count_fixed_eval_questions(db) == 0:
            seeded = seed_fixed_eval_questions_from_file(db, seed_path)
            logger.info("Seeded fixed evaluation dataset rows=%d from %s", seeded, seed_path.name)
    finally:
        db.close()


def _load_fixed_rows(seed_path: Path) -> List[DatasetRow]:
    _ensure_fixed_dataset_seeded(seed_path)
    db = SessionLocal()
    try:
        rows = list_fixed_eval_questions(db)
        return [
            {
                "id": f"fixed:{row.id}",
                "row_id": row.id,
                "question": row.question,
                "expected_answer": row.expected_answer,
                "context": None,
                "source": "fixed",
                "topic": row.topic,
                "difficulty": row.difficulty,
            }
            for row in rows
        ]
    finally:
        db.close()


def _score_with_azure(rows: List[Dict[str, Any]], include_similarity: bool) -> List[Dict[str, Optional[float]]]:
    try:
        from azure.ai.evaluation import evaluate, GroundednessEvaluator, RelevanceEvaluator, SimilarityEvaluator  # type: ignore
    except Exception as e:
        raise RuntimeError("Azure AI Evaluation SDK is required. Install `azure-ai-evaluation`.") from e

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    if not endpoint or not api_key or not deployment:
        raise RuntimeError(
            "Missing Azure OpenAI env vars: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_CHAT_DEPLOYMENT."
        )

    model_config = {
        "azure_endpoint": endpoint,
        "api_key": api_key,
        "azure_deployment": deployment,
        "api_version": api_version,
    }
    logger.info(
        "Azure AI Evaluation enabled. deployment=%s api_version=%s include_similarity=%s",
        deployment,
        api_version,
        include_similarity,
    )
    batch_size = max(1, int(os.getenv("EVAL_AZURE_BATCH_SIZE", "5")))
    batch_sleep_seconds = max(0.0, float(os.getenv("EVAL_AZURE_BATCH_SLEEP_SECONDS", "2.0")))

    def score_single_batch(batch_rows: List[Dict[str, Any]], batch_index: int, batch_count: int) -> List[Dict[str, Optional[float]]]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            data_path = f.name
            for row in batch_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        try:
            evaluators: Dict[str, Any] = {
                "groundedness": GroundednessEvaluator(model_config),
                "relevance": RelevanceEvaluator(model_config),
            }
            evaluator_config: Dict[str, Dict[str, Dict[str, str]]] = {
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
            }
            if include_similarity:
                evaluators["similarity"] = SimilarityEvaluator(model_config)
                evaluator_config["similarity"] = {
                    "column_mapping": {
                        "query": "${data.question}",
                        "response": "${data.answer}",
                        "ground_truth": "${data.ground_truth}",
                    }
                }

            logger.info(
                "Azure AI Evaluation batch %d/%d starting rows=%d include_similarity=%s",
                batch_index,
                batch_count,
                len(batch_rows),
                include_similarity,
            )
            result = evaluate(data=data_path, evaluators=evaluators, evaluator_config=evaluator_config)
            eval_rows = result.get("rows", []) if isinstance(result, dict) else []
            if not eval_rows:
                raise RuntimeError(f"Azure AI Evaluation returned no rows for batch {batch_index}/{batch_count}.")

            metrics: List[Dict[str, Optional[float]]] = []
            for row in eval_rows:
                groundedness, _ = _extract_score(row, "groundedness")
                relevance, _ = _extract_score(row, "relevance")
                similarity = None
                if include_similarity:
                    similarity_raw, similarity_key = _extract_score(row, "similarity")
                    if similarity_key is not None:
                        similarity = max(0.0, min(5.0, similarity_raw))

                groundedness = max(0.0, min(5.0, groundedness))
                relevance = max(0.0, min(5.0, relevance))
                components = [groundedness, relevance]
                if similarity is not None:
                    components.append(similarity)
                overall = round(sum(components) / len(components), 4)
                metrics.append(
                    {
                        "groundedness": round(groundedness, 4),
                        "relevance": round(relevance, 4),
                        "similarity": round(similarity, 4) if similarity is not None else None,
                        "overall_score": overall,
                    }
                )
            logger.info(
                "Azure AI Evaluation batch %d/%d finished rows=%d",
                batch_index,
                batch_count,
                len(metrics),
            )
            return metrics
        except Exception as exc:
            if "ratelimit" in str(exc).lower() or "429" in str(exc):
                raise RuntimeError(
                    "Azure AI Evaluation hit rate limits. Reduce evaluation batch size, wait and retry, "
                    "or increase Azure OpenAI quota for the judge deployment."
                ) from exc
            raise
        finally:
            try:
                os.remove(data_path)
            except Exception:
                pass

    batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
    logger.info(
        "Azure AI Evaluation batching enabled total_rows=%d batch_size=%d batches=%d sleep_seconds=%.2f",
        len(rows),
        batch_size,
        len(batches),
        batch_sleep_seconds,
    )

    all_metrics: List[Dict[str, Optional[float]]] = []
    for index, batch_rows in enumerate(batches, start=1):
        all_metrics.extend(score_single_batch(batch_rows, index, len(batches)))
        if index < len(batches) and batch_sleep_seconds > 0:
            time.sleep(batch_sleep_seconds)
    return all_metrics


def _evaluate_rows(
    rows: List[DatasetRow],
    search_service: HybridSearchService,
    gpt_client: GPTClient,
    top_k: int,
) -> List[EvaluationResult]:
    rows_for_eval: List[Dict[str, Any]] = []
    results: List[EvaluationResult] = []
    fixed_ok_indexes: List[int] = []

    for row in rows:
        try:
            search_results, _ = search_service.hybrid_search(query=row["question"], top_k=top_k)
            chunks = [str(item.get("content", "")).strip() for item in search_results if str(item.get("content", "")).strip()]
            context = _build_context(chunks)
            if not context:
                raise RuntimeError("No retrieved chunks found.")

            answer = _generate_eval_answer(
                gpt_client=gpt_client,
                question=row["question"],
                context=context,
            )

            rows_for_eval.append(
                {
                    "question": row["question"],
                    "answer": answer,
                    "context": context,
                    "ground_truth": row.get("expected_answer") or "",
                }
            )
            if row["source"] == "fixed":
                fixed_ok_indexes.append(len(rows_for_eval) - 1)

            results.append(
                EvaluationResult(
                    id=row["id"],
                    question=row["question"],
                    expected_answer=row.get("expected_answer"),
                    generated_answer=answer,
                    retrieved_chunks=chunks,
                    groundedness=0.0,
                    relevance=0.0,
                    similarity=None,
                    overall_score=0.0,
                    status="ok",
                    source=row["source"],
                    topic=row.get("topic"),
                    difficulty=row.get("difficulty"),
                )
            )
        except Exception as e:
            if _is_content_filter_error(e):
                logger.warning(
                    "Evaluation skipped due to Azure content filter for question id=%s error=%s",
                    row.get("id"),
                    e,
                )
            else:
                logger.exception("Evaluation failed for question id=%s: %s", row.get("id"), e)
            results.append(
                EvaluationResult(
                    id=row.get("id"),
                    question=row["question"],
                    expected_answer=row.get("expected_answer"),
                    generated_answer="",
                    retrieved_chunks=[],
                    groundedness=0.0,
                    relevance=0.0,
                    similarity=None,
                    overall_score=0.0,
                    status="error",
                    error=str(e),
                    source=row["source"],
                    topic=row.get("topic"),
                    difficulty=row.get("difficulty"),
                )
            )

    if rows_for_eval:
        include_similarity = any(result.source == "fixed" and result.status == "ok" for result in results)
        metrics = _score_with_azure(rows_for_eval, include_similarity=include_similarity)
        ok_results = [result for result in results if result.status == "ok"]
        if len(metrics) != len(ok_results):
            raise RuntimeError("Evaluation row count mismatch.")
        for result, metric in zip(ok_results, metrics):
            result.groundedness = float(metric["groundedness"] or 0.0)
            result.relevance = float(metric["relevance"] or 0.0)
            result.similarity = float(metric["similarity"]) if metric["similarity"] is not None and result.source == "fixed" else None
            result.overall_score = float(metric["overall_score"] or 0.0)

    return results


def _summarize_results(source: Literal["fixed", "synthetic", "both", "overall"], results: List[EvaluationResult]) -> EvaluationSummary:
    total = len(results)
    ok_results = [row for row in results if row.status == "ok"]
    failed = total - len(ok_results)
    if not ok_results:
        return EvaluationSummary(
            source=source,
            total=total,
            ok=0,
            failed=failed,
            avg_groundedness=0.0,
            avg_relevance=0.0,
            avg_overall=0.0,
            avg_similarity=None,
        )

    fixed_ok = [row for row in ok_results if row.similarity is not None]
    avg_similarity = None
    if fixed_ok:
        avg_similarity = round(sum(float(row.similarity or 0.0) for row in fixed_ok) / len(fixed_ok), 4)

    return EvaluationSummary(
        source=source,
        total=total,
        ok=len(ok_results),
        failed=failed,
        avg_groundedness=round(sum(row.groundedness for row in ok_results) / len(ok_results), 4),
        avg_relevance=round(sum(row.relevance for row in ok_results) / len(ok_results), 4),
        avg_overall=round(sum(row.overall_score for row in ok_results) / len(ok_results), 4),
        avg_similarity=avg_similarity,
    )


def _store_run_summaries(mode: DatasetSource, summaries: List[EvaluationSummary]) -> str:
    db = SessionLocal()
    run_id = str(uuid4())
    try:
        for summary in summaries:
            if summary.source not in ("fixed", "synthetic"):
                continue
            create_evaluation_run(
                db=db,
                mode=mode,
                dataset_source=str(summary.source),
                avg_groundedness=summary.avg_groundedness,
                avg_relevance=summary.avg_relevance,
                avg_overall=summary.avg_overall,
                avg_similarity=summary.avg_similarity,
                total_questions=summary.total,
                succeeded=summary.ok,
                failed=summary.failed,
            )
    finally:
        db.close()
    return run_id


def _load_regression_points(dataset_source: Literal["fixed", "synthetic"]) -> List[EvaluationRegressionPoint]:
    db = SessionLocal()
    try:
        runs = list_evaluation_runs(db, dataset_source=dataset_source, limit=20)
        return [
            EvaluationRegressionPoint(
                run_id=run.id,
                run_label=run.run_label,
                timestamp=run.created_at,
                dataset_source=run.dataset_source,
                avg_groundedness=run.avg_groundedness,
                avg_relevance=run.avg_relevance,
                avg_overall=run.avg_overall,
                avg_similarity=run.avg_similarity,
            )
            for run in reversed(runs)
        ]
    finally:
        db.close()


def _load_regression_history(mode: DatasetSource) -> EvaluationRegressionHistory:
    history = EvaluationRegressionHistory()
    if mode in ("fixed", "both"):
        history.fixed = _load_regression_points("fixed")
    if mode in ("synthetic", "both"):
        history.synthetic = _load_regression_points("synthetic")
    return history


def run_automated_evaluation(
    dataset_source: DatasetSource = "synthetic",
    synthetic_only_unused: bool = True,
    synthetic_limit: int = 200,
) -> AutomatedEvalResponse:
    ensure_tables()

    repo_root = Path(__file__).resolve().parents[2]
    fixed_seed_path = repo_root / "data" / "fixed_eval_dataset.json"
    top_k = int(os.getenv("EVAL_TOP_K", "5"))

    fixed_rows: List[DatasetRow] = []
    synthetic_rows: List[DatasetRow] = []

    if dataset_source in ("fixed", "both"):
        fixed_rows = _load_fixed_rows(fixed_seed_path)
    if dataset_source in ("synthetic", "both"):
        synthetic_rows = _load_synthetic_rows(only_unused=synthetic_only_unused, limit=synthetic_limit)
        if not synthetic_rows:
            logger.info("No synthetic evaluation rows found. Triggering background backfill.")
            trigger_synthetic_eval_backfill_background(max_documents=2, pipeline_version="synthetic-v2")
            if dataset_source == "synthetic":
                raise ValueError(
                    "No evaluation rows found for selected dataset_source. "
                    "Synthetic dataset generation has been triggered in the background; retry after it completes."
                )
        synthetic_rows = _sample_rows(synthetic_rows, max_rows=20)

    selected_rows: List[DatasetRow]
    if dataset_source == "fixed":
        selected_rows = fixed_rows
    elif dataset_source == "synthetic":
        selected_rows = synthetic_rows
    else:
        selected_rows = _sample_rows(_dedupe_rows_by_question([*synthetic_rows, *fixed_rows]), max_rows=30)

    if not selected_rows:
        raise ValueError("No evaluation rows found for selected dataset_source.")

    logger.info(
        "Starting evaluation mode=%s rows=%d fixed_rows=%d synthetic_rows=%d",
        dataset_source,
        len(selected_rows),
        sum(1 for row in selected_rows if row["source"] == "fixed"),
        sum(1 for row in selected_rows if row["source"] == "synthetic"),
    )

    search_client = get_azure_search_client()
    embedding_client = AzureOpenAIEmbeddingClient()
    search_service = HybridSearchService(search_client=search_client, embedding_client=embedding_client)
    gpt_client = GPTClient()

    results = _evaluate_rows(selected_rows, search_service=search_service, gpt_client=gpt_client, top_k=top_k)

    summaries: List[EvaluationSummary] = []
    fixed_results = [row for row in results if row.source == "fixed"]
    synthetic_results = [row for row in results if row.source == "synthetic"]

    if dataset_source in ("fixed", "both") and fixed_results:
        summaries.append(_summarize_results("fixed", fixed_results))
    if dataset_source in ("synthetic", "both") and synthetic_results:
        summaries.append(_summarize_results("synthetic", synthetic_results))

    overall_source: Literal["fixed", "synthetic", "both"]
    if dataset_source == "fixed":
        overall_source = "fixed"
    elif dataset_source == "synthetic":
        overall_source = "synthetic"
    else:
        overall_source = "both"
    overall_summary = _summarize_results(overall_source, results)
    if dataset_source == "both":
        summaries = [overall_summary, *summaries]
    else:
        summaries = [overall_summary]

    run_id = _store_run_summaries(dataset_source, summaries)

    synthetic_ids = [row["row_id"] for row in selected_rows if row["source"] == "synthetic" and row.get("row_id")]
    if synthetic_ids:
        db = SessionLocal()
        try:
            marked = mark_synthetic_eval_rows_used(db, ids=synthetic_ids)
            logger.info("Marked synthetic eval rows used count=%d", marked)
        finally:
            db.close()

    return AutomatedEvalResponse(
        run_id=run_id,
        mode=dataset_source,
        dataset_source=dataset_source,
        provider_used="azure_ai_evaluation",
        summary=overall_summary,
        summaries=summaries,
        results=results,
        regression_history=_load_regression_history(dataset_source),
        evaluated_at=datetime.now(timezone.utc),
    )
