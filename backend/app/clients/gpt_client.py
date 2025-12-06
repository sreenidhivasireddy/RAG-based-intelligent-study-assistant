"""
GPT-4o 客户端
用于替代 DeepSeekClient，实现流式对话生成
"""
import os
import logging
from typing import List, Dict, Callable, Optional
from openai import OpenAI
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class GPTClient:
    """
    GPT-4o 客户端，支持流式响应和 RAG 上下文注入
    """
    
    def __init__(self):
        """
        初始化 GPT 客户端
        
        Args:
            api_key: OpenAI API 密钥，默认从环境变量 OPENAI_API_KEY 读取
            api_base: API 基础地址，用于自定义端点或代理
            model: 模型名称，默认 gpt-4o
            temperature: 生成温度 (0-2)
            top_p: 核采样参数 (0-1)
            max_tokens: 最大生成 token 数
            system_rules: 系统指令
            ref_start: 参考信息起始标记
            ref_end: 参考信息结束标记
            no_result_text: 无检索结果时的占位文本
        """
        # 从环境变量读取配置，参数优先级高于环境变量
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = os.getenv("OPENAI_API_BASE")  # 支持 DeepSeek 等兼容端点
        self.model = os.getenv("GPT_MODEL", "gpt-4o")
        self.temperature = float(os.getenv("GPT_TEMPERATURE", "0.7"))
        self.top_p = float(os.getenv("GPT_TOP_P", "0.95"))
        self.max_tokens = int(os.getenv("GPT_MAX_TOKENS", "2000"))
        self.rules = os.getenv("GPT_SYSTEM_RULES", "You are PaiSmart knowledge assistant. Please answer user questions accurately based on the provided reference information. When citing sources, mention the source file names clearly.")
        self.ref_start = os.getenv("GPT_REF_START", "<<REF>>")
        self.ref_end = os.getenv("GPT_REF_END", "<<END>>")
        self.no_result_text = os.getenv("GPT_NO_RESULT_TEXT", "(No retrieval results for this round)")
        
        # 初始化客户端
        client_kwargs = {"api_key": self.api_key}
        if self.api_base:
            client_kwargs["base_url"] = self.api_base
            
        self.client = OpenAI(**client_kwargs)
        self.async_client = AsyncOpenAI(**client_kwargs)
        
        logger.info(f"GPT 客户端初始化完成，模型: {self.model}")
    
    def stream_response(
        self,
        user_message: str,
        context: str,
        history: Optional[List[Dict[str, str]]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> str:
        """
        流式调用 GPT-4o，逐块返回响应
        
        Args:
            user_message: 用户当前提问
            context: 检索到的文档上下文（RAG）
            history: 历史对话记录 [{"role": "user", "content": "..."},...]
            on_chunk: 每收到一块内容时的回调函数
            on_error: 错误处理回调函数
            
        Returns:
            完整的 AI 响应文本
        """
        try:
            logger.info(
                f"开始流式调用 GPT-4o，用户消息长度: {len(user_message)}, "
                f"上下文长度: {len(context) if context else 0}, "
                f"历史消息数: {len(history) if history else 0}"
            )
            
            # 1. 构建消息列表
            messages = self._build_messages(user_message, context, history)
            
            # 2. 调用 OpenAI API（流式）
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stream=True  # 启用流式响应
            )
            
            # 3. 逐块处理响应
            full_response = ""
            for chunk in stream:
                content = self._process_chunk(chunk)
                if content:
                    full_response += content
                    if on_chunk:
                        try:
                            on_chunk(content)
                        except Exception as callback_error:
                            logger.error(f"on_chunk 回调执行失败: {callback_error}")
            
            logger.info(f"GPT-4o 响应完成，总长度: {len(full_response)}")
            return full_response
        
        except Exception as e:
            logger.error(f"GPT-4o 调用失败: {e}", exc_info=True)
            if on_error:
                on_error(e)
            raise

    async def stream_response_async(
        self,
        user_message: str,
        context: str,
        history: Optional[List[Dict[str, str]]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> str:
        """
        异步版本的流式调用（适用于 FastAPI/asyncio）
        """
        try:
            messages = self._build_messages(user_message, context, history)
            
            # 使用异步客户端（复用初始化的实例）
            async_client = self.async_client
            
            stream = await async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
                stream=True
            )
            
            full_response = ""
            async for chunk in stream:
                content = self._process_chunk(chunk)
                if content:
                    full_response += content
                    if on_chunk:
                        on_chunk(content)
            return full_response
            
        except Exception as e:
            logger.error(f"异步 GPT-4o 调用失败: {e}")
            if on_error:
                on_error(e)
            raise
    
    def _build_messages(
        self,
        user_message: str,
        context: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """
        构建符合 OpenAI API 格式的消息列表
        实现 RAG 的 Prompt 工程
        
        返回格式:
        [
            {"role": "system", "content": "规则 + 检索上下文"},
            {"role": "user", "content": "历史问题1"},
            {"role": "assistant", "content": "历史回答1"},
            {"role": "user", "content": "当前问题"}
        ]
        """
        messages = []
        
        # 1. 构建 System 消息（规则 + 检索上下文）
        system_parts = [self.rules, ""]
        
        # 添加参考信息
        system_parts.append(self.ref_start)
        if context and context.strip():
            system_parts.append(context)
        else:
            system_parts.append(self.no_result_text)
        system_parts.append(self.ref_end)
        
        system_content = "\n".join(system_parts)
        messages.append({
            "role": "system",
            "content": system_content
        })
        
        logger.debug(f"添加系统消息，长度: {len(system_content)}")
        
        # 2. 添加历史对话
        if history:
            for msg in history:
                # 只保留 role 和 content，过滤 timestamp 等额外字段
                if "role" in msg and "content" in msg:
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            logger.debug(f"添加历史消息数: {len(history)}")
        
        # 3. 添加当前用户问题
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages

    def _process_chunk(self, chunk) -> str:
        """
        处理流式响应的每一块数据
        提取实际的文本内容
        
        Args:
            chunk: OpenAI 的流式响应块
            
        Returns:
            提取的文本内容
        """
        try:
            # OpenAI SDK 的流式响应格式
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    return delta.content
            return ""
        except Exception as e:
            logger.error(f"处理响应块失败: {e}")
            return ""