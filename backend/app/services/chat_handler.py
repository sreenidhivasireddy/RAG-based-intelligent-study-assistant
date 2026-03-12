from typing import List, Dict, Callable, Optional, Set
from collections import defaultdict
from uuid import uuid4
import logging
import json
import time
from datetime import datetime, timedelta
from app.clients.gpt_client import GPTClient
from app.services.search import HybridSearchService
from app.services.file_content_service import FileContentService
from app.database import SessionLocal
from app.repositories.upload_repository import get_file_upload, get_all_file_uploads
import redis
from scripts.explain_file import explain_document
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_\-\s]", " ", (value or "").lower())


def _upload_sort_key(upload) -> float:
    """
    Robust timestamp key for upload ordering.
    Prefers merged_at, then created_at; handles None/str/datetime safely.
    """
    ts = getattr(upload, "merged_at", None) or getattr(upload, "created_at", None)
    if ts is None:
        return 0.0
    if isinstance(ts, datetime):
        return ts.timestamp()
    # Fallback for string or other timestamp-like values
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


class ChatHandler:
    """
    Manages conversation history based on session_id (not dependent on userId).

    Dependencies:
      - llm_client: provides stream_response_async(user_message, context, history, on_chunk)
      - search_service: provides hybrid_search(query, top_k) -> List[results]
      - file_content_service: provides fallback file content retrieval
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        llm_client: GPTClient,
        search_service: HybridSearchService,
        conversation_id: str = "default_conversation",
        max_history: int = 20,
        file_content_service: FileContentService = None
    ):
        """
        Initialize the chat handler.

        Args:
            redis_client: Redis client
            llm_client: LLM client (e.g., GPT-4o)
            search_service: Hybrid search service instance
            conversation_id: Conversation ID (fixed or provided by frontend)
            max_history: Maximum number of stored history messages
            file_content_service: Optional file content service for fallback retrieval
        """
        self.redis = redis_client
        self.llm_client = llm_client
        self.search_service = search_service
        self.conversation_id = conversation_id
        self.max_history = max_history
        self.file_content_service = file_content_service or FileContentService()

        logger.info(f"ChatHandler initialized. Conversation ID: {conversation_id}")

    async def process_message(
        self,
        user_message: str,
        websocket=None,
        top_k: int = 5
    ) -> str:
        """
        Process a user message asynchronously (for FastAPI WebSocket use).

        Args:
            user_message: User input message
            websocket: WebSocket connection object
            top_k: Number of documents to retrieve

        Returns:
            Full AI response
        """
        try:
            logger.info(f"Processing message asynchronously. Conversation ID: {self.conversation_id}")
            websocket_alive = True

            async def _safe_send_json(payload: dict) -> bool:
                nonlocal websocket_alive
                if not websocket or not websocket_alive:
                    return False
                try:
                    await websocket.send_json(payload)
                    return True
                except (WebSocketDisconnect, RuntimeError):
                    websocket_alive = False
                    logger.info("WebSocket disconnected while sending message; stopping stream for this request.")
                    return False
                except Exception:
                    websocket_alive = False
                    logger.warning("WebSocket send failed; stopping stream for this request.", exc_info=True)
                    return False

            # 1. Retrieve conversation history
            history = self._get_conversation_history()

            # 2. Check if message references a filename; if so try direct retrieval first
            # Special-case: messages starting with "Explain <filename>" -> run explanation flow
            try:
                import re
                m_explain = re.match(r"^\s*Explain\s+(.+)$", user_message, re.IGNORECASE)
                if m_explain and websocket:
                    filename_quoted = m_explain.group(1).strip()
                    # Resolve filename to latest file_md5 using uploads
                    db_res = SessionLocal()
                    try:
                        uploads = get_all_file_uploads(db=db_res, skip=0, limit=1000)
                        # find candidates matching base name or full name
                        fname_lower = filename_quoted.lower()
                        candidates = [u for u in uploads if u.file_name and (u.file_name.lower() == fname_lower or u.file_name.lower().endswith(fname_lower) or u.file_name.lower().split('.')[0] == fname_lower)]
                        if not candidates:
                            # try contains
                            candidates = [u for u in uploads if u.file_name and fname_lower in u.file_name.lower()]
                        if candidates:
                            # pick most recent by created_at
                            candidates.sort(key=_upload_sort_key, reverse=True)
                            chosen = candidates[0]
                            # Run explanation and stream result back
                            await _safe_send_json({"type": "info", "message": f"Running explanation for {chosen.file_name}"})
                            # call explain_document
                            result = await explain_document(chosen.file_md5, question=None)
                            resp = result.get('response', '')
                            citations = result.get('citations', [])
                            # stream in chunks
                            chunk_size = 500
                            for i in range(0, len(resp), chunk_size):
                                chunk = resp[i:i+chunk_size]
                                await _safe_send_json({"chunk": chunk})
                            await _safe_send_json({"type": "completion", "status": "finished", "source_files": [chosen.file_name], "citations": citations})
                            return resp
                        else:
                            await _safe_send_json({"type": "error", "message": f"No uploaded file matches '{filename_quoted}'"})
                            return ""
                    finally:
                        db_res.close()
            except Exception:
                # if explanation flow fails, continue to normal processing
                pass

            forced_context = None
            forced_source_files = set()
            forced_file_md5 = None
            try:
                scoped_file = self._get_conversation_scoped_file()
                if scoped_file:
                    forced_file_md5 = scoped_file["file_md5"]
                    forced_source_files.add(scoped_file["file_name"])
                    logger.info(
                        "Using conversation-scoped file for retrieval: %s (%s)",
                        scoped_file["file_name"],
                        scoped_file["file_md5"],
                    )

                # Handle requests like "summarize this file" by binding to latest upload.
                if self._is_latest_file_reference(user_message):
                    latest_file = self._get_latest_uploaded_file(preferred_file_md5=forced_file_md5)
                    if latest_file:
                        forced_file_md5 = latest_file.file_md5
                        forced_source_files.add(latest_file.file_name)
                        db_latest = SessionLocal()
                        try:
                            latest_content = self.file_content_service.get_file_content_by_md5(
                                file_md5=latest_file.file_md5,
                                db=db_latest
                            )
                            if latest_content:
                                forced_context = f"[File: {latest_file.file_name}] " + latest_content[:4000]
                                forced_source_files.add(latest_file.file_name)
                                forced_file_md5 = latest_file.file_md5
                                logger.info(
                                    "Resolved latest-file reference to %s (%s)",
                                    latest_file.file_name,
                                    latest_file.file_md5
                                )
                        finally:
                            db_latest.close()

                # First try explicit filename with extension
                if not forced_context and (".txt" in user_message.lower() or ".pdf" in user_message.lower() or ".docx" in user_message.lower()):
                    import re
                    m = re.search(r"([\w\-\. ]+\.(txt|pdf|docx))", user_message, re.IGNORECASE)
                    if m:
                        filename = m.group(1).strip()
                        db_for_name = SessionLocal()
                        try:
                            file_content = self.file_content_service.get_file_content_by_filename(filename, db_for_name)
                            if file_content:
                                    forced_context = f"[File: {filename}] " + (file_content[:2000])
                                    forced_source_files.add(filename)
                                    # resolve md5 by scanning uploads (get_file_upload expects md5, not filename)
                                    try:
                                        all_uploads = get_all_file_uploads(db=db_for_name, skip=0, limit=1000)
                                        filename_lower = filename.lower()
                                        for rec in all_uploads:
                                            rec_name = (rec.file_name or "").lower()
                                            if rec_name == filename_lower:
                                                forced_file_md5 = rec.file_md5
                                                break
                                    except Exception:
                                        pass
                                    logger.info(f"Direct file retrieval for filename mentioned in message: {filename}")
                        finally:
                            db_for_name.close()

                # If no explicit extension was mentioned, try matching uploaded file names
                if not forced_context and not forced_file_md5:
                    try:
                        import re
                        db_scan = SessionLocal()
                        try:
                            uploads = get_all_file_uploads(db=db_scan, skip=0, limit=1000)
                            if uploads:
                                # extract alphanumeric tokens (include underscore and hyphen)
                                tokens = set(re.findall(r"[A-Za-z0-9_\-]+", user_message.lower()))
                                def normalize(s: str) -> str:
                                    return re.sub(r"[^a-z0-9_\-]", "", s.lower() or "")
                                candidate = None
                                # prefer exact filename, then base-name, then contains
                                for u in uploads:
                                    name = (u.file_name or "").strip()
                                    if not name:
                                        continue
                                    name_lower = name.lower()
                                    base_lower = name_lower.rsplit('.', 1)[0]

                                    # normalized comparison for robustness
                                    norm_name = normalize(name_lower)
                                    norm_base = normalize(base_lower)
                                    # exact filename/token match
                                    if norm_name in tokens or norm_name == normalize(user_message):
                                        candidate = name
                                        break

                                    # base name token match
                                    if norm_base in tokens and candidate is None:
                                        candidate = name

                                if candidate:
                                    # find upload record for candidate
                                    candidate_rec = None
                                    for u in uploads:
                                        if (u.file_name or "").strip().lower() == candidate.lower():
                                            candidate_rec = u
                                            break

                                    file_content = self.file_content_service.get_file_content_by_filename(candidate, db_scan)
                                    if file_content:
                                        forced_context = f"[File: {candidate}] " + (file_content[:2000])
                                        forced_source_files.add(candidate)
                                        if candidate_rec:
                                            forced_file_md5 = candidate_rec.file_md5
                                        logger.info(f"Direct file retrieval for filename matched in DB: {candidate}")
                        finally:
                            db_scan.close()
                    except Exception:
                        # Ignore DB scan failures and continue to hybrid search
                        pass
            except Exception:
                # Fail silently and continue to hybrid search
                forced_context = None

            # 3. Perform hybrid search (skipped if forced_context is present)
            if forced_context is None:
                search_results, search_metadata = self.search_service.hybrid_search(
                    query=user_message,
                    top_k=top_k,
                    file_md5_filter=forced_file_md5
                )
            else:
                search_results = []
                search_metadata = {}

            # 3. Lookup file names from database
            file_name_cache = self._lookup_file_names(search_results)

            # 4. Build context with file names (or use forced content)
            if forced_context:
                context = forced_context
                source_files = forced_source_files
            else:
                context, source_files = self._build_context(search_results, file_name_cache)

            # 5. FALLBACK: If search returns no results, try to retrieve from uploaded files
                if not search_results or not context.strip():
                    logger.warning("⚠️ Search returned no results. Attempting fallback file retrieval...")
                fallback_context, fallback_files = await self._get_fallback_context(
                    user_message,
                    preferred_file_md5=forced_file_md5
                )
                
                if fallback_context:
                    context = fallback_context
                    source_files = fallback_files
                    logger.info(f"✅ Fallback retrieval successful. Found {len(source_files)} files with content.")
                else:
                    logger.warning("❌ Fallback retrieval also returned no results.")

            # 6. Define WebSocket chunk sender
            async def send_chunk(chunk: str):
                await _safe_send_json({"chunk": chunk})

            # 7. Call LLM asynchronously
            full_response = await self.llm_client.stream_response_async(
                user_message=user_message,
                context=context,
                history=history,
                # Send chunks in-order; avoid scheduling detached tasks that can
                # arrive after completion and create UI race conditions.
                on_chunk=send_chunk
            )

            # 8. Send completion notification
            if websocket_alive:
                await _safe_send_json({
                    "type": "completion",
                    "status": "finished",
                    "message": "Response completed",
                    "timestamp": int(time.time() * 1000),
                    "source_files": list(source_files),
                    "response": full_response
                })

            # 9. Update conversation history
            self._update_conversation_history(user_message, full_response)

            return full_response

        except Exception as e:
            logger.error(f"Failed to process message asynchronously: {e}", exc_info=True)
            if websocket and websocket_alive:
                await _safe_send_json({
                    "error": "AI service is temporarily unavailable. Please try again later."
                })
            raise

    def _get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Retrieve conversation history from Redis.

        Returns:
            List of history messages
        """
        key = f"conversation:{self.conversation_id}"

        try:
            json_str = self.redis.get(key)

            if json_str is None:
                logger.debug(f"No history found for conversation {self.conversation_id}")
                return []

            history = json.loads(json_str)
            logger.debug(f"Retrieved {len(history)} history messages for {self.conversation_id}")
            return history

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode conversation history: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to retrieve conversation history: {e}")
            return []

    def _update_conversation_history(self, user_message: str, assistant_response: str):
        """
        Update conversation history in Redis.
        """
        key = f"conversation:{self.conversation_id}"

        try:
            history = self._get_conversation_history()

            current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            history.append({
                "role": "user",
                "content": user_message,
                "timestamp": current_timestamp
            })

            history.append({
                "role": "assistant",
                "content": assistant_response,
                "timestamp": current_timestamp
            })

            if len(history) > self.max_history:
                history = history[-self.max_history:]

            json_str = json.dumps(history, ensure_ascii=False)
            self.redis.setex(key, timedelta(days=7), json_str)

            logger.debug(f"Conversation history updated. Total messages: {len(history)}")

        except Exception as e:
            logger.error(f"Failed to update conversation history: {e}", exc_info=True)

    def _lookup_file_names(self, search_results: List[Dict]) -> Dict[str, str]:
        """
        Retrieve file names from database using file_md5.
        """
        file_name_cache = {}
        unique_md5s = set(r.get("file_md5") for r in search_results if r.get("file_md5"))

        if not unique_md5s:
            return file_name_cache

        db = SessionLocal()
        try:
            for md5 in unique_md5s:
                file_upload = get_file_upload(db, md5)
                if file_upload:
                    file_name_cache[md5] = file_upload.file_name
        except Exception as e:
            logger.error(f"Failed to query file names: {e}", exc_info=True)
        finally:
            db.close()

        return file_name_cache

    def _build_context(self, search_results: List[Dict], file_name_cache: Dict[str, str]) -> tuple[str, Set[str]]:
        """
        Build formatted retrieval context including file names.
        """
        if not search_results:
            return "", set()

        MAX_SNIPPET_LEN = 300
        context_parts = []
        source_files = set()
        valid_result_idx = 0

        for result in search_results:
            text_content = result.get('content', result.get('text_content', result.get('textContent', '')))

            if len(text_content) > MAX_SNIPPET_LEN:
                text_content = text_content[:MAX_SNIPPET_LEN] + "..."

            file_md5 = result.get('file_md5')
            file_name = file_name_cache.get(file_md5) if file_md5 else None
            # Skip stale index hits that no longer have a backing file record.
            if file_md5 and not file_name:
                logger.info("Skipping stale search hit for deleted file_md5=%s", file_md5)
                continue

            if not file_name:
                file_name = result.get('file_name', result.get('fileName', 'unknown'))

            if file_name and file_name != 'unknown':
                source_files.add(file_name)

            valid_result_idx += 1
            context_parts.append(f"[{valid_result_idx}] Source: {file_name}\nContent: {text_content}")

        context = "\n".join(context_parts)
        logger.debug(f"Context built. Length: {len(context)}, Source files: {len(source_files)}")

        return context, source_files

    async def _get_fallback_context(
        self,
        user_message: str,
        preferred_file_md5: str | None = None
    ) -> tuple[str, Set[str]]:
        """
        Retrieve content from uploaded files when search-based retrieval fails.
        
        Strategy:
        1. Get all uploaded files
        2. For each file, check for relevant content (matching keywords from user message)
        3. Return combined context with all relevant file snippets
        
        Args:
            user_message: User's query message
            
        Returns:
            Tuple of (combined context, set of source files)
        """
        try:
            db = SessionLocal()
            context_parts = []
            source_files = set()
            
            try:
                # Get all completed/available files (status=1 is completed, status=2 is merged)
                logger.info("Getting all uploaded files for fallback retrieval...")
                
                all_files = []
                
                # Try status=1 (completed files)
                completed_files = get_all_file_uploads(
                    db=db,
                    skip=0,
                    limit=1000,
                    status_filter=1
                )
                if completed_files:
                    all_files.extend(completed_files)
                    logger.info(f"Found {len(completed_files)} completed files (status=1)")
                
                # Also try status=2 (merged files waiting for processing)
                merged_files = get_all_file_uploads(
                    db=db,
                    skip=0,
                    limit=1000,
                    status_filter=2
                )
                if merged_files:
                    all_files.extend(merged_files)
                    logger.info(f"Found {len(merged_files)} merged files (status=2)")
                
                if not all_files:
                    logger.warning("❌ No files found for fallback retrieval (status 1 or 2)")
                    return "", set()
                
                # Prioritize newest files first so recent uploads are attempted early.
                all_files.sort(key=_upload_sort_key, reverse=True)

                # If we know the user means a specific uploaded file (e.g., "this file"),
                # force that file to be attempted first.
                if preferred_file_md5:
                    preferred = [f for f in all_files if f.file_md5 == preferred_file_md5]
                    others = [f for f in all_files if f.file_md5 != preferred_file_md5]
                    if preferred:
                        all_files = preferred + others
                        logger.info(f"Preferred fallback file set to MD5={preferred_file_md5}")

                # Fast-path: if preferred file is available, try it first and return immediately.
                if preferred_file_md5:
                    preferred_file = next((f for f in all_files if f.file_md5 == preferred_file_md5), None)
                    if preferred_file:
                        try:
                            preferred_content = self.file_content_service.get_file_content_by_md5(
                                file_md5=preferred_file.file_md5,
                                db=db
                            )
                            if preferred_content and preferred_content.strip():
                                logger.info(
                                    f"Using preferred uploaded file first: {preferred_file.file_name} "
                                    f"({len(preferred_content)} chars)"
                                )
                                return (
                                    f"[File: {preferred_file.file_name}] {preferred_content[:3000]}...",
                                    {preferred_file.file_name}
                                )
                        except Exception:
                            logger.warning("Preferred file fast-path retrieval failed; falling back to normal scan.", exc_info=True)
                logger.info(f"✅ Attempting fallback retrieval from {len(all_files)} total files")
                
                # Try to get content from each file. Prioritize files whose names match
                # tokens from the user message (so filename mentions are tried first).
                successful_files = 0
                max_files_to_try = 5
                files_tried = 0
                started_at = time.time()
                max_seconds = 20

                # Build token set and prioritize matching files
                import re
                tokens = set(re.findall(r"[A-Za-z0-9_\-]+", user_message.lower()))
                def _norm(s: str) -> str:
                    return re.sub(r"[^a-z0-9_\-]", "", (s or "").lower())

                matching = []
                others = []
                for fr in all_files:
                    name = (fr.file_name or "").strip().lower()
                    base = name.rsplit('.', 1)[0] if name else ""
                    if _norm(base) in tokens or _norm(name) in tokens:
                        matching.append(fr)
                    else:
                        others.append(fr)

                if preferred_file_md5:
                    processing_order = matching + others
                elif matching:
                    processing_order = matching
                else:
                    logger.info(
                        "No filename/token matches found in uploaded files for fallback; "
                        "skipping broad fallback scan."
                    )
                    return "", set()

                logger.info(f"Fallback tokens: {tokens}; matching files: {[f.file_name for f in matching]}")

                for file_record in processing_order:
                    if (time.time() - started_at) > max_seconds:
                        logger.info(f"Fallback retrieval time budget reached ({max_seconds}s).")
                        break
                    if files_tried >= max_files_to_try:
                        logger.info(f"Reached max files limit ({max_files_to_try}) for fallback retrieval")
                        break
                    
                    files_tried += 1
                    
                    try:
                        logger.debug(f"Processing file: {file_record.file_name} (MD5: {file_record.file_md5}, status: {file_record.status}, size: {file_record.total_size})")
                        
                        # First try to get file snippets from database
                        snippets = self.file_content_service.get_file_snippets(
                            file_md5=file_record.file_md5,
                            db=db,
                            max_snippets=3  # Get first 3 snippets per file
                        )
                        
                        if snippets:
                            logger.info(f"✅ Retrieved {len(snippets)} snippets from file {file_record.file_name}")
                            
                            for idx, snippet in enumerate(snippets, 1):
                                content = snippet.get('content', '')[:300]  # Limit to 300 chars
                                context_parts.append(
                                    f"[File: {file_record.file_name}] {content}..."
                                )
                            
                            source_files.add(file_record.file_name)
                            successful_files += 1
                        else:
                            logger.debug(f"⚠️ No snippets found in database for {file_record.file_name}")
                            
                            # Try to get full file content if no snippets available
                            try:
                                file_content = self.file_content_service.get_file_content_by_md5(
                                    file_md5=file_record.file_md5,
                                    db=db
                                )
                                
                                if file_content:
                                    logger.info(f"✅ Retrieved full content from file {file_record.file_name} ({len(file_content)} chars)")
                                    context_parts.append(
                                        f"[File: {file_record.file_name}] {file_content[:500]}..."
                                    )
                                    source_files.add(file_record.file_name)
                                    successful_files += 1
                                    # Prefer fast answer over broad aggregation.
                                    if preferred_file_md5:
                                        break
                                else:
                                    logger.debug(f"Could not retrieve content for {file_record.file_name}")
                            except Exception as content_error:
                                logger.debug(f"Error getting full content for {file_record.file_name}: {content_error}")
                    
                    except Exception as e:
                        logger.warning(f"Error retrieving content from file {file_record.file_name}: {e}")
                        continue
                
                # Build combined context
                if context_parts:
                    context = "\n\n".join(context_parts)
                    logger.info(f"✅ Fallback context built successfully. Length: {len(context)}, Files: {len(source_files)}, Successful: {successful_files}")
                    return context, source_files
                else:
                    logger.warning(f"❌ No content available from any of the {len(all_files)} files")
                    return "", set()
            
            finally:
                db.close()
        
        except Exception as e:
            logger.error(f"Error in fallback context retrieval: {e}", exc_info=True)
            return "", set()

    def _is_latest_file_reference(self, user_message: str) -> bool:
        text = _normalize_text(user_message)
        keywords = [
            "this file",
            "the file",
            "uploaded file",
            "latest file",
            "that file",
            "summarize this",
            "explain this file",
            "what is this file",
        ]
        return any(k in text for k in keywords)

    def _get_latest_uploaded_file(self, preferred_file_md5: str | None = None):
        db = SessionLocal()
        try:
            candidates = []
            completed = get_all_file_uploads(db=db, skip=0, limit=1000, status_filter=1)
            merged = get_all_file_uploads(db=db, skip=0, limit=1000, status_filter=2)
            if completed:
                candidates.extend(completed)
            if merged:
                candidates.extend(merged)
            if not candidates:
                return None
            if preferred_file_md5:
                preferred = [c for c in candidates if c.file_md5 == preferred_file_md5]
                if preferred:
                    preferred.sort(key=_upload_sort_key, reverse=True)
                    return preferred[0]
            candidates.sort(key=_upload_sort_key, reverse=True)
            return candidates[0]
        finally:
            db.close()

    def _get_conversation_scoped_file(self) -> Optional[Dict[str, str]]:
        try:
            raw = self.redis.get(f"conversation_meta:{self.conversation_id}")
            if not raw:
                return None
            meta = json.loads(raw)
            latest_file_md5 = str(meta.get("latest_file_md5", "")).strip()
            latest_file_name = str(meta.get("latest_file_name", "")).strip()
            if latest_file_md5 and latest_file_name:
                return {
                    "file_md5": latest_file_md5,
                    "file_name": latest_file_name,
                }

            attached_files = meta.get("attached_files") or []
            if attached_files:
                latest = attached_files[-1]
                file_md5 = str(latest.get("file_md5", "")).strip()
                file_name = str(latest.get("file_name", "")).strip()
                if file_md5 and file_name:
                    return {
                        "file_md5": file_md5,
                        "file_name": file_name,
                    }
        except Exception as exc:
            logger.warning("Failed to read conversation-scoped file metadata: %s", exc)
        return None

    def clear_history(self):
        """Clear conversation history."""
        key = f"conversation:{self.conversation_id}"
        self.redis.delete(key)
        logger.info(f"Conversation {self.conversation_id} history cleared")

    def get_history(self) -> List[Dict[str, str]]:
        """Return conversation history."""
        return self._get_conversation_history()

    def set_conversation_id(self, conversation_id: str):
        """Switch to a new conversation ID."""
        self.conversation_id = conversation_id
        logger.info(f"Switched to new conversation: {conversation_id}")
