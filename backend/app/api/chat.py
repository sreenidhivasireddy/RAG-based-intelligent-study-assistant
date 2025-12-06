# api/chat_routes.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import logging

from app.clients.redis import redis_client
from app.clients.gpt_client import GPTClient
from app.clients.elastic import es_client
from app.clients.gemini_embedding_client import GeminiEmbeddingClient
from app.services.search import HybridSearchService
from app.services.chat_handler import ChatHandler

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize shared services
gpt_client_instance = GPTClient()
embedding_client = GeminiEmbeddingClient()
hybrid_search_service = HybridSearchService(
    es_client=es_client,
    embedding_client=embedding_client
)


@router.websocket("/ws/{conversation_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    conversation_id: str
):
    """
    WebSocket 聊天接口
    对应 Java 的 ChatController.handleTextMessage()
    
    前端连接:
        ws://localhost:8000/api/v1/chat/ws/my_conversation_123
    
    发送格式:
        {"message": "你好，什么是 RAG？"}
    
    接收格式:
        {"chunk": "RAG"}  # 流式响应
        {"type": "completion", "status": "finished"}  # 完成通知
    """
    await websocket.accept()
    logger.info(f"✅ WebSocket 连接已建立，会话ID: {conversation_id}")
    
    # 创建 ChatHandler
    chat_handler = ChatHandler(
        redis_client=redis_client,
        llm_client=gpt_client_instance,
        search_service=hybrid_search_service,
        conversation_id=conversation_id
    )
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            
            if not user_message:
                await websocket.send_json({
                    "error": "消息不能为空"
                })
                continue
            
            logger.info(f"📨 收到消息: {user_message[:50]}...")
            
            # 处理消息（核心调用）
            try:
                await chat_handler.process_message(
                    user_message=user_message,
                    websocket=websocket
                )
            except Exception as e:
                logger.error(f"❌ 处理消息失败: {e}", exc_info=True)
                await websocket.send_json({
                    "error": f"处理消息失败: {str(e)}"
                })
    
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 连接已关闭，会话ID: {conversation_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket 异常: {e}", exc_info=True)
        try:
            await websocket.close()
        except:
            pass


@router.get("/websocket-token")
async def get_websocket_token():
    """
    获取 WebSocket 停止指令 Token
    对应 Java 的 ChatController.getWebSocketToken()
    
    注：简化版本可能不需要这个，直接通过特殊消息格式停止即可
    """
    # 简化版本：生成一个临时 token
    import secrets
    token = secrets.token_urlsafe(16)
    
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "获取 WebSocket Token 成功",
            "data": {"cmdToken": token}
        }
    )