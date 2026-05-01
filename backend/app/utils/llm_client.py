"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
import httpx
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            **kwargs: 其他传递给大模型的参数 (如 frequency_penalty)
            
        Returns:
            模型响应文本
        """
        call_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        call_kwargs.update(kwargs)
        
        if response_format:
            call_kwargs["response_format"] = response_format
        
        call_kwargs.setdefault("timeout", 600)
        response = self.client.chat.completions.create(**call_kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        try:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )

            cleaned_response = response.strip()
            cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
            cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
            cleaned_response = cleaned_response.strip()

            return json.loads(cleaned_response)
        except (httpx.HTTPStatusError, Exception) as e:
            fallback_response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            cleaned_fallback = fallback_response.strip()
            cleaned_fallback = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_fallback, flags=re.IGNORECASE)
            cleaned_fallback = re.sub(r'\n?```\s*$', '', cleaned_fallback)
            cleaned_fallback = cleaned_fallback.strip()

            json_match = re.search(r'\{[\s\S]*\}', cleaned_fallback)
            if not json_match:
                raise ValueError(f"無法從純文字回應中提取 JSON: {cleaned_fallback}")

            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError as json_e:
                raise ValueError(f"純文字回應提取的 JSON 格式無效: {json_match.group(0)}") from json_e

    def close(self):
        """釋放 httpx 連線資源"""
        if hasattr(self, 'client') and hasattr(self.client, '_client'):
            try:
                self.client.close()
            except:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
