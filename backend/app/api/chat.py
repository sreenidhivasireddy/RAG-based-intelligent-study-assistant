# api/chat_routes.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import logging
from starlette.websockets import WebSocketState

from app.clients.redis import redis_client
from app.clients.gpt_client import GPTClient
from app.clients.azure_search import get_azure_search_client
from app.clients.azure_openai_embedding_client import AzureOpenAIEmbeddingClient
from app.services.search import HybridSearchService
from app.services.chat_handler import ChatHandler
from app.services.file_content_service import FileContentService

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize shared services
gpt_client_instance = GPTClient()
embedding_client = AzureOpenAIEmbeddingClient()
azure_search_client = get_azure_search_client()
hybrid_search_service = HybridSearchService(
    search_client=azure_search_client,
    embedding_client=embedding_client
)
file_content_service = FileContentService()


async def _safe_ws_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        if websocket.client_state != WebSocketState.CONNECTED:
            return False
        await websocket.send_json(payload)
        return True
    except Exception:
        return False


@router.websocket("/ws/{conversation_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    conversation_id: str
):
    """
    WebSocket chat endpoint.
    Equivalent to Java's ChatController.handleTextMessage().

    Frontend connection:
        ws://localhost:8000/api/v1/chat/ws/my_conversation_123

    Send format:
        {"message": "Hello, what is RAG?"}

    Receive format:
        {"chunk": "RAG"}  # Streaming response
        {"type": "completion", "status": "finished"}  # Completion notice
    """
    await websocket.accept()
    logger.info(f"WebSocket connection established, conversation ID: {conversation_id}")
    
    # Create ChatHandler with file content service for tracking.
    chat_handler = ChatHandler(
        redis_client=redis_client,
        llm_client=gpt_client_instance,
        search_service=hybrid_search_service,
        conversation_id=conversation_id,
        file_content_service=file_content_service
    )
    
    try:
        while True:
            # Receive messages.
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            
            if not user_message:
                await _safe_ws_send_json(websocket, {
                    "error": "Message cannot be empty"
                })
                continue
            
            logger.info(f"Received message: {user_message[:50]}...")
            
            # Process the message.
            try:
                await chat_handler.process_message(
                    user_message=user_message,
                    websocket=websocket
                )
            except Exception as e:
                logger.error(f"Failed to process message: {e}", exc_info=True)
                await _safe_ws_send_json(websocket, {
                    "error": f"Failed to process message: {str(e)}"
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed, conversation ID: {conversation_id}")
    except Exception as e:
        logger.error(f"WebSocket exception: {e}", exc_info=True)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except:
            pass


@router.get("/websocket-token")
async def get_websocket_token():
    """
    Get a WebSocket stop-command token.
    Equivalent to Java's ChatController.getWebSocketToken().

    Note: the simplified version may not need this; a special message can stop the stream directly.
    """
    # Simplified version: generate a temporary token.
    import secrets
    token = secrets.token_urlsafe(16)
    
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "WebSocket token retrieved successfully",
            "data": {"cmdToken": token}
        }
    )
