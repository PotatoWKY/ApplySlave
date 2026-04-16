"""LLM 客户端 — 封装 Ollama API 调用"""

from __future__ import annotations

import json
from typing import Optional

from loguru import logger

try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False


class LLMClient:
    """Ollama LLM 客户端，支持优雅降级"""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._available: Optional[bool] = None
        self._client = None

    async def is_available(self) -> bool:
        """检查 Ollama 是否可用"""
        if self._available is not None:
            return self._available
        if not HAS_OLLAMA:
            logger.warning("ollama 包未安装")
            self._available = False
            return False
        try:
            self._client = ollama.AsyncClient(host=self._base_url)
            models = await self._client.list()
            model_names = [m.model for m in models.models]
            logger.info(f"Ollama 可用，模型列表: {model_names}")
            if not any(self._model in name for name in model_names):
                logger.warning(f"模型 {self._model} 未找到，可用模型: {model_names}")
            self._available = True
        except Exception as e:
            logger.warning(f"Ollama 不可用: {e}")
            self._available = False
        return self._available

    async def ask_json(self, prompt: str) -> Optional[dict]:
        """发送 prompt，期望返回 JSON，自动重试解析失败"""
        if not await self.is_available():
            return None

        for attempt in range(self._max_retries):
            try:
                response = await self._client.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.1},
                )
                raw = response.message.content.strip()
                logger.debug(f"LLM 原始输出 (attempt {attempt+1}): {raw[:200]}")

                # 提取 JSON — 处理 markdown code block
                json_str = self._extract_json(raw)
                result = json.loads(json_str)
                return result

            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败 (attempt {attempt+1}/{self._max_retries}): {e}")
            except Exception as e:
                logger.error(f"LLM 调用失败 (attempt {attempt+1}/{self._max_retries}): {e}")
                break

        return None

    def _extract_json(self, text: str) -> str:
        """从 LLM 输出中提取 JSON 字符串"""
        # 去掉 markdown code block
        if "```json" in text:
            text = text.split("```json", 1)[1]
            text = text.split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1]
            text = text.split("```", 1)[0]

        # 找到第一个 { 或 [
        for i, c in enumerate(text):
            if c in "{[":
                # 找到对应的闭合
                depth = 0
                for j in range(i, len(text)):
                    if text[j] in "{[":
                        depth += 1
                    elif text[j] in "}]":
                        depth -= 1
                    if depth == 0:
                        return text[i:j+1]
                break

        return text.strip()
