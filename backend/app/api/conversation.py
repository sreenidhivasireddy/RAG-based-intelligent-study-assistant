# api/conversation_routes.py

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
import json
import logging

from app.clients.redis import redis_client
from app.utils.datetime_parser import parse_datetime

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    start_date: Optional[str] = Query(
        None,
        description="起始时间 (YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)"
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束时间 (YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS)"
    )
):
    """
    获取对话历史（支持时间过滤）
    对应 Java 的 ConversationController.getConversations()
    
    返回示例:
        {
            "code": 200,
            "message": "获取对话历史成功",
            "data": [
                {
                    "role": "user",
                    "content": "什么是 RAG？",
                    "timestamp": "2025-01-01T10:00:00"
                },
                ...
            ]
        }
    """
    try:
        logger.info(f"📜 获取对话历史，会话ID: {conversation_id}")
        
        # 从 Redis 获取历史
        key = f"conversation:{conversation_id}"
        json_str = await redis_client.get(key)
        
        if not json_str:
            logger.info(f"⚠️ 会话 {conversation_id} 没有历史记录")
            return JSONResponse(
                status_code=200,
                content={
                    "code": 200,
                    "message": "获取对话历史成功",
                    "data": []
                }
            )
        
        # 解析历史
        history = json.loads(json_str)
        logger.debug(f"从 Redis 读取到 {len(history)} 条消息")
        
        # 时间过滤
        filtered_history = _filter_by_time(
            history,
            start_date,
            end_date
        )
        
        logger.info(
            f"✅ 返回 {len(filtered_history)} 条历史记录"
            f"（共 {len(history)} 条）"
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "获取对话历史成功",
                "data": filtered_history
            }
        )
    
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 解析失败: {e}")
        raise HTTPException(
            status_code=500,
            detail="解析对话历史失败"
        )
    except Exception as e:
        logger.error(f"❌ 获取对话历史失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部错误: {str(e)}"
        )


@router.delete("/{conversation_id}")
async def clear_conversation_history(conversation_id: str):
    """
    清空对话历史
    对应 Java 的 ConversationController（假设有删除接口）
    
    返回示例:
        {
            "code": 200,
            "message": "对话历史已清空"
        }
    """
    try:
        logger.info(f"🗑️ 清空对话历史，会话ID: {conversation_id}")
        
        key = f"conversation:{conversation_id}"
        deleted = await redis_client.delete(key)
        
        if deleted:
            logger.info(f"✅ 会话 {conversation_id} 的历史已清空")
        else:
            logger.info(f"⚠️ 会话 {conversation_id} 本来就没有历史记录")
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": f"会话 {conversation_id} 的历史已清空"
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 清空对话历史失败: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部错误: {str(e)}"
        )


@router.get("/{conversation_id}/summary")
async def get_conversation_summary(conversation_id: str):
    """
    获取对话摘要信息
    
    返回示例:
        {
            "code": 200,
            "data": {
                "conversation_id": "abc123",
                "total_messages": 10,
                "user_messages": 5,
                "assistant_messages": 5
            }
        }
    """
    try:
        key = f"conversation:{conversation_id}"
        json_str = await redis_client.get(key)
        
        if not json_str:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 200,
                    "message": "会话不存在或无历史记录",
                    "data": None
                }
            )
        
        history = json.loads(json_str)
        
        # 统计信息
        user_msgs = [m for m in history if m.get("role") == "user"]
        assistant_msgs = [m for m in history if m.get("role") == "assistant"]
        
        timestamps = [
            m.get("timestamp")
            for m in history
            if m.get("timestamp")
        ]
        
        summary = {
            "conversation_id": conversation_id,
            "total_messages": len(history),
            "user_messages": len(user_msgs),
            "assistant_messages": len(assistant_msgs),
            "first_message_time": timestamps[0] if timestamps else None,
            "last_message_time": timestamps[-1] if timestamps else None
        }
        
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "获取摘要成功",
                "data": summary
            }
        )
    
    except Exception as e:
        logger.error(f"❌ 获取摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助函数 ====================

def _filter_by_time(
    history: list,
    start_date: Optional[str],
    end_date: Optional[str]
) -> list:
    """按时间过滤历史消息"""
    if not start_date and not end_date:
        return history
    
    start_dt = parse_datetime(start_date) if start_date else None
    end_dt = parse_datetime(end_date) if end_date else None
    
    filtered = []
    for msg in history:
        msg_timestamp = msg.get("timestamp")
        
        if not msg_timestamp or msg_timestamp == "未知时间":
            continue
        
        try:
            msg_dt = datetime.strptime(
                msg_timestamp,
                "%Y-%m-%dT%H:%M:%S"
            )
            
            if start_dt and msg_dt < start_dt:
                continue
            if end_dt and msg_dt > end_dt:
                continue
            
            filtered.append(msg)
        except ValueError:
            logger.warning(f"⚠️ 无效的时间戳: {msg_timestamp}")
            continue
    
    return filtered