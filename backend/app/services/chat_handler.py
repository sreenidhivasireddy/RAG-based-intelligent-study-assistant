from typing import List, Dict, Callable, Optional, Set
from collections import defaultdict
from uuid import uuid4
import logging
import json
import asyncio
import time
from datetime import datetime, timedelta
from app.clients.gpt_client import GPTClient
from app.services.search import HybridSearchService
from app.database import SessionLocal
from app.repositories.upload_repository import get_file_upload
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
        llm_client: GPTClient,
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
    
    async def process_message(
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
            search_results, search_metadata = self.search_service.hybrid_search(
                query=user_message,
                top_k=top_k
            )
            
            # 3. 查询文件名
            file_name_cache = self._lookup_file_names(search_results)
            
            # 4. 构建上下文（包含文件名）
            context, source_files = self._build_context(search_results, file_name_cache)
            
            # 5. 定义 WebSocket 推送回调
            async def send_chunk(chunk: str):
                if websocket:
                    await websocket.send_json({"chunk": chunk})
            
            # 6. 调用 LLM（异步）
            full_response = await self.llm_client.stream_response_async(
                user_message=user_message,
                context=context,
                history=history,
                on_chunk=lambda chunk: asyncio.create_task(send_chunk(chunk))
            )
            
            # 7. 发送完成通知（包含源文件列表）
            if websocket:
                await websocket.send_json({
                    "type": "completion",
                    "status": "finished",
                    "message": "Response completed",
                    "timestamp": int(time.time() * 1000),
                    "source_files": list(source_files)  # 返回使用的源文件列表
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
    
    def _lookup_file_names(self, search_results: List[Dict]) -> Dict[str, str]:
        """
        从数据库查询文件名
        
        Args:
            search_results: 检索结果列表（包含 file_md5）
            
        Returns:
            文件名缓存字典 {file_md5: file_name}
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
            logger.error(f"查询文件名失败: {e}", exc_info=True)
        finally:
            db.close()
        
        return file_name_cache
    
    def _build_context(self, search_results: List[Dict], file_name_cache: Dict[str, str]) -> tuple[str, Set[str]]:
        """
        构建检索上下文，包含文件名信息
        
        Args:
            search_results: 检索结果列表
            file_name_cache: 文件名缓存字典 {file_md5: file_name}
            
        Returns:
            (格式化的上下文字符串, 使用的源文件集合)
        """
        if not search_results:
            return "", set()
        
        MAX_SNIPPET_LEN = 300
        context_parts = []
        source_files = set()
        
        for i, result in enumerate(search_results, 1):
            # 提取文本内容
            text_content = result.get('text_content', result.get('textContent', ''))
            
            # 截断过长的片段
            if len(text_content) > MAX_SNIPPET_LEN:
                text_content = text_content[:MAX_SNIPPET_LEN] + "..."
            
            # 获取文件名（优先从缓存，其次从结果，最后使用 unknown）
            file_md5 = result.get('file_md5')
            file_name = file_name_cache.get(file_md5) if file_md5 else None
            if not file_name:
                file_name = result.get('file_name', result.get('fileName', 'unknown'))
            
            # 添加到源文件集合
            if file_name and file_name != 'unknown':
                source_files.add(file_name)
            
            # 格式化：[序号] Source: file_name\nContent: text_content
            context_parts.append(f"[{i}] Source: {file_name}\nContent: {text_content}")
        
        context = "\n".join(context_parts)
        logger.debug(f"构建上下文完成，长度: {len(context)}, 源文件数: {len(source_files)}")
        
        return context, source_files

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