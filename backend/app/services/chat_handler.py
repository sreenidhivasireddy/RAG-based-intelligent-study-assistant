from typing import List, Dict, Callable
from collections import defaultdict
from uuid import uuid4
import logging
from app.clients.gpt_client import GptClient
from app.services.search_service import HybridSearchService
import redis
logger = logging.getLogger(__name__)

class ChatHandler:
    """
    基于 session_id 管理对话历史，不依赖 userId。
    需要依赖：
      - llm_client: 提供 stream_response(user_message, context, history, on_chunk, on_error)
      - search_service: 提供 search(query, top_k) -> List[结果对象，含 textContent/content 和可选 fileName]
    """
     
    def __init__(
        self,
        redis_client: redis.Redis,
        llm_client: GptClient,
        search_service: HybridSearchService,
        conversation_id: str = "default_conversation",
        max_history: int = 20
    ):
        """
        初始化聊天处理器
        
        Args:
            redis_client: Redis 客户端
            llm_client: LLM 客户端（GPT-4o/DeepSeek）
            search_service: 检索服务实例
            conversation_id: 会话 ID（固定或由前端传入）
            max_history: 保留的最大历史消息数
        """
        self.redis = redis_client
        self.llm_client = llm_client
        self.search_service = search_service
        self.conversation_id = conversation_id
        self.max_history = max_history
        
        logger.info(f"ChatHandler 初始化完成，会话ID: {conversation_id}")
    
    def process_message(
        self,
        user_message: str,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        top_k: int = 5
    ):
        """
        处理用户消息（同步版本）
        
        Args:
            user_message: 用户输入的消息
            on_chunk: 收到流式响应块时的回调
            on_complete: 响应完成时的回调
            on_error: 发生错误时的回调
            top_k: 检索返回的文档数量
            
        Returns:
            完整的 AI 响应
        """
        try:
            logger.info(f"开始处理消息，会话ID: {self.conversation_id}")
            
            # 1. 获取对话历史
            history = self._get_conversation_history()
            logger.debug(f"获取到 {len(history)} 条历史对话")
            
            # 2. 执行检索（不带用户权限过滤）
            search_results = self.search_service.search(
                query=user_message,
                top_k=top_k
            )
            logger.debug(f"检索结果数量: {len(search_results)}")
            
            # 3. 构建上下文
            context = self._build_context(search_results)
            
            # 4. 调用 LLM 流式响应
            logger.info("调用 LLM 生成回复")
            
            full_response = self.llm_client.stream_response(
                user_message=user_message,
                context=context,
                history=history,
                on_chunk=on_chunk,
                on_error=on_error
            )
            # 5. 发送完成通知
            if on_complete:
                on_complete(full_response)
            
            # 6. 更新对话历史
            self._update_conversation_history(user_message, full_response)
            
            logger.info(f"消息处理完成，响应长度: {len(full_response)}")
            return full_response

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            if on_error:
                on_error(e)
            raise
    

    async def process_message_async(
        self,
        user_message: str,
        websocket=None,  # WebSocket 连接对象
        top_k: int = 5
    ) -> str:
        """
        处理用户消息（异步版本 - 适用于 FastAPI WebSocket）
        
        Args:
            user_message: 用户输入的消息
            websocket: WebSocket 连接对象
            top_k: 检索返回的文档数量
            
        Returns:
            完整的 AI 响应
        """
        try:
            logger.info(f"开始异步处理消息，会话ID: {self.conversation_id}")
            
            # 1. 获取对话历史
            history = self._get_conversation_history()
            
            # 2. 执行检索
            search_results = self.search_service.search(
                query=user_message,
                top_k=top_k
            )
            # 3. 构建上下文
            context = self._build_context(search_results)
            
            # 4. 定义 WebSocket 推送回调
            async def send_chunk(chunk: str):
                if websocket:
                    await websocket.send_json({"chunk": chunk})
            
            # 5. 调用 LLM（异步）
            full_response = await self.llm_client.stream_response_async(
                user_message=user_message,
                context=context,
                history=history,
                on_chunk=lambda chunk: asyncio.create_task(send_chunk(chunk))
            )
            
            # 6. 发送完成通知
            if websocket:
                await websocket.send_json({
                    "type": "completion",
                    "status": "finished",
                    "message": "响应已完成",
                    "timestamp": int(time.time() * 1000)
                })
            
            # 7. 更新历史
            self._update_conversation_history(user_message, full_response)
            
            return full_response

        except Exception as e:
            logger.error(f"异步处理消息失败: {e}", exc_info=True)
            if websocket:
                await websocket.send_json({
                    "error": "AI 服务暂时不可用，请稍后重试"
                })
            raise
    
    def _get_conversation_history(self) -> List[Dict[str, str]]:
        """
        从 Redis 获取对话历史
        
        Returns:
            历史消息列表 [{"role": "user", "content": "..."}, ...]
        """
        key = f"conversation:{self.conversation_id}"
        
        try:
            json_str = self.redis.get(key)
            
            if json_str is None:
                logger.debug(f"会话 {self.conversation_id} 没有历史记录")
                return []
            
            history = json.loads(json_str)
            logger.debug(f"读取到会话 {self.conversation_id} 的 {len(history)} 条历史记录")
            return history
            
        except json.JSONDecodeError as e:
            logger.error(f"解析对话历史失败: {e}")
            return []
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []

    def _update_conversation_history(
        self,
        user_message: str,
        assistant_response: str
    ):
        """
        更新对话历史到 Redis
        
        Args:
            user_message: 用户消息
            assistant_response: AI 回复
        """
        key = f"conversation:{self.conversation_id}"
        
        try:
            # 获取现有历史
            history = self._get_conversation_history()
            
            # 获取当前时间戳
            current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            # 添加用户消息
            history.append({
                "role": "user",
                "content": user_message,
                "timestamp": current_timestamp
            })
            
            # 添加助手回复
            history.append({
                "role": "assistant",
                "content": assistant_response,
                "timestamp": current_timestamp
            })
            # 限制历史长度（保留最近 N 条）
            if len(history) > self.max_history:
                history = history[-self.max_history:]
            
            # 序列化并存储到 Redis（TTL 7天）
            json_str = json.dumps(history, ensure_ascii=False)
            self.redis.setex(key, timedelta(days=7), json_str)
            
            logger.debug(f"更新会话历史，会话ID: {self.conversation_id}, 总消息数: {len(history)}")
            
        except Exception as e:
            logger.error(f"更新对话历史失败: {e}", exc_info=True)
    
    def _build_context(self, search_results: List[Dict]) -> str:
        """
        构建检索上下文
        
        Args:
            search_results: 检索结果列表
            
        Returns:
            格式化的上下文字符串
        """
        if not search_results:
            return ""
        
        MAX_SNIPPET_LEN = 300
        context_parts = []
        
        for i, result in enumerate(search_results, 1):
            # 提取文本内容
            text_content = result.get('text_content', result.get('textContent', ''))
            
            # 截断过长的片段
            if len(text_content) > MAX_SNIPPET_LEN:
                text_content = text_content[:MAX_SNIPPET_LEN] + "…"
            
            # 提取文件名
            file_name = result.get('file_name', result.get('fileName', 'unknown'))
            
            # 格式化：[序号] (文件名) 内容
            context_parts.append(f"[{i}] ({file_name}) {text_content}")
        
        context = "\n".join(context_parts)
        logger.debug(f"构建上下文完成，长度: {len(context)}")
        
        return context

    def clear_history(self):
        """清空当前会话的历史记录"""
        key = f"conversation:{self.conversation_id}"
        self.redis.delete(key)
        logger.info(f"已清空会话 {self.conversation_id} 的历史记录")
    
    
    def get_history(self) -> List[Dict[str, str]]:
        """
        获取当前会话的历史记录（供前端查询）
        
        Returns:
            历史消息列表
        """
        return self._get_conversation_history()
    
    
    def set_conversation_id(self, conversation_id: str):
        """
        切换到新的会话 ID
        
        Args:
            conversation_id: 新的会话 ID
        """
        self.conversation_id = conversation_id
        logger.info(f"切换到新会话: {conversation_id}")