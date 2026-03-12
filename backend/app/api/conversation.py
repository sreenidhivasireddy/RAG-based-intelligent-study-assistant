# api/conversation_routes.py

from fastapi import APIRouter, Query, HTTPException, Body
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
import json
import logging

from app.clients.redis import redis_client
from app.utils.datetime_parser import parse_datetime

logger = logging.getLogger(__name__)
router = APIRouter()


TTL_SECONDS = 7 * 24 * 60 * 60


def _conversation_key(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


def _conversation_meta_key(conversation_id: str) -> str:
    return f"conversation_meta:{conversation_id}"


def _read_conversation_history(conversation_id: str) -> list:
    raw = redis_client.get(_conversation_key(conversation_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _write_conversation_history(conversation_id: str, history: list) -> None:
    redis_client.setex(
        _conversation_key(conversation_id),
        TTL_SECONDS,
        json.dumps(history, ensure_ascii=False),
    )


def _read_conversation_meta(conversation_id: str) -> dict:
    raw = redis_client.get(_conversation_meta_key(conversation_id))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _write_conversation_meta(conversation_id: str, meta: dict) -> None:
    redis_client.setex(
        _conversation_meta_key(conversation_id),
        TTL_SECONDS,
        json.dumps(meta, ensure_ascii=False),
    )


@router.post("/")
async def create_conversation(conversation_id: Optional[str] = None):
    """
    Create a new empty conversation so it appears immediately in the sidebar.
    """
    try:
        conv_id = conversation_id or f"conv_{int(datetime.now().timestamp() * 1000)}"
        now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        if redis_client.get(_conversation_key(conv_id)) is None:
            _write_conversation_history(conv_id, [])

        meta = _read_conversation_meta(conv_id)
        if not meta:
            meta = {
                "title": "New Conversation",
                "created_at": now_ts,
                "last_message_time": now_ts,
            }
            _write_conversation_meta(conv_id, meta)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Conversation created",
                "data": {
                    "conversation_id": conv_id,
                    "title": meta.get("title", "New Conversation"),
                    "message_count": 0,
                    "first_message_time": None,
                    "last_message_time": meta.get("last_message_time"),
                    "preview": "",
                },
            },
        )
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{conversation_id}/title")
async def rename_conversation(conversation_id: str, payload: dict = Body(...)):
    """
    Rename an existing conversation title.
    """
    try:
        title = str(payload.get("title", "")).strip()
        if not title:
            raise HTTPException(status_code=400, detail="title is required")

        history = _read_conversation_history(conversation_id)
        meta = _read_conversation_meta(conversation_id)

        if not history and not meta:
            raise HTTPException(status_code=404, detail=f"Conversation not found: {conversation_id}")

        now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        meta["title"] = title[:50]
        meta.setdefault("created_at", now_ts)
        meta["last_message_time"] = now_ts
        _write_conversation_meta(conversation_id, meta)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Conversation renamed",
                "data": {
                    "conversation_id": conversation_id,
                    "title": meta["title"],
                },
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conversation_id}/files")
async def attach_file_to_conversation(conversation_id: str, payload: dict = Body(...)):
    """
    Attach an uploaded file to a conversation so chat retrieval can be scoped to it.
    """
    try:
        file_md5 = str(payload.get("file_md5", "")).strip()
        file_name = str(payload.get("file_name", "")).strip()
        if not file_md5 or not file_name:
            raise HTTPException(status_code=400, detail="file_md5 and file_name are required")

        history = _read_conversation_history(conversation_id)
        meta = _read_conversation_meta(conversation_id)
        if not history and not meta:
            now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            _write_conversation_history(conversation_id, [])
            meta = {
                "title": "New Conversation",
                "created_at": now_ts,
                "last_message_time": now_ts,
            }

        attached_files = meta.get("attached_files") or []
        attached_files = [
            item for item in attached_files
            if str(item.get("file_md5", "")).strip() != file_md5
        ]

        now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        attached_files.append(
            {
                "file_md5": file_md5,
                "file_name": file_name,
                "attached_at": now_ts,
            }
        )
        meta["attached_files"] = attached_files
        meta["latest_file_md5"] = file_md5
        meta["latest_file_name"] = file_name
        meta["last_message_time"] = now_ts
        meta.setdefault("created_at", now_ts)
        _write_conversation_meta(conversation_id, meta)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "File attached to conversation",
                "data": {
                    "conversation_id": conversation_id,
                    "file_md5": file_md5,
                    "file_name": file_name,
                    "attached_files": attached_files,
                },
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to attach file to conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_all_conversations():
    try:
        logger.info("Loading all conversations")

        history_keys = redis_client.keys("conversation:*")
        meta_keys = redis_client.keys("conversation_meta:*")

        conversation_ids = set()

        for key in history_keys:
            raw = key if isinstance(key, str) else key.decode()
            if raw.startswith("conversation:"):
                conversation_ids.add(raw.replace("conversation:", ""))

        for key in meta_keys:
            raw = key if isinstance(key, str) else key.decode()
            if raw.startswith("conversation_meta:"):
                conversation_ids.add(raw.replace("conversation_meta:", ""))

        conversations = []

        for conv_id in conversation_ids:
            try:
                history = _read_conversation_history(conv_id)
                meta = _read_conversation_meta(conv_id)

                first_user_msg = next((m for m in history if m.get("role") == "user"), None)

                if meta.get("title") and meta.get("title") != "New Conversation":
                    title = str(meta.get("title"))[:50]
                else:
                    title = first_user_msg.get("content", "New Conversation")[:50] if first_user_msg else "New Conversation"
                    if len(first_user_msg.get("content", "") if first_user_msg else "") > 50:
                        title += "..."

                last_msg = history[-1] if history else None
                preview = ""
                if last_msg:
                    preview = last_msg.get("content", "")[:100]
                    if len(last_msg.get("content", "")) > 100:
                        preview += "..."

                timestamps = [m.get("timestamp") for m in history if m.get("timestamp")]
                first_time = timestamps[0] if timestamps else meta.get("created_at")
                last_time = timestamps[-1] if timestamps else meta.get("last_message_time")

                conversations.append(
                    {
                        "conversation_id": conv_id,
                        "title": title or "New Conversation",
                        "message_count": len(history),
                        "first_message_time": first_time,
                        "last_message_time": last_time,
                        "preview": preview,
                    }
                )
            except Exception as inner_e:
                logger.warning(f"Failed to parse conversation {conv_id}: {inner_e}")
                continue

        conversations.sort(key=lambda x: x.get("last_message_time") or "", reverse=True)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Success",
                "data": conversations,
            },
        )

    except Exception as e:
        logger.error(f"Failed to load conversation list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    start_date: Optional[str] = Query(
        None,
        description="Start time (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End time (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)",
    ),
):
    try:
        logger.info(f"Getting conversation history: {conversation_id}")

        history = _read_conversation_history(conversation_id)

        if not history:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 200,
                    "message": "Success",
                    "data": [],
                },
            )

        filtered_history = _filter_by_time(history, start_date, end_date)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Success",
                "data": filtered_history,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.delete("/{conversation_id}")
async def clear_conversation_history(conversation_id: str):
    try:
        logger.info(f"Clearing conversation history: {conversation_id}")

        deleted_history = redis_client.delete(_conversation_key(conversation_id))
        deleted_meta = redis_client.delete(_conversation_meta_key(conversation_id))

        if deleted_history or deleted_meta:
            msg = f"Conversation {conversation_id} cleared"
        else:
            msg = f"Conversation {conversation_id} had no data"

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": msg,
            },
        )

    except Exception as e:
        logger.error(f"Failed to clear conversation history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/{conversation_id}/summary")
async def get_conversation_summary(conversation_id: str):
    try:
        history = _read_conversation_history(conversation_id)
        if not history:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 200,
                    "message": "Conversation not found or empty",
                    "data": None,
                },
            )

        user_msgs = [m for m in history if m.get("role") == "user"]
        assistant_msgs = [m for m in history if m.get("role") == "assistant"]
        timestamps = [m.get("timestamp") for m in history if m.get("timestamp")]

        summary = {
            "conversation_id": conversation_id,
            "total_messages": len(history),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "first_message_time": timestamps[0] if timestamps else None,
            "last_message_time": timestamps[-1] if timestamps else None,
        }

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Summary fetched",
                "data": summary,
            },
        )

    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== helper ====================

def _filter_by_time(
    history: list,
    start_date: Optional[str],
    end_date: Optional[str],
) -> list:
    """Filter messages by timestamp range."""
    if not start_date and not end_date:
        return history

    start_dt = parse_datetime(start_date) if start_date else None
    end_dt = parse_datetime(end_date) if end_date else None

    filtered = []
    for msg in history:
        msg_timestamp = msg.get("timestamp")

        if not msg_timestamp:
            continue

        try:
            msg_dt = datetime.strptime(msg_timestamp, "%Y-%m-%dT%H:%M:%S")
            if start_dt and msg_dt < start_dt:
                continue
            if end_dt and msg_dt > end_dt:
                continue
            filtered.append(msg)
        except ValueError:
            logger.warning(f"Invalid timestamp: {msg_timestamp}")
            continue

    return filtered
