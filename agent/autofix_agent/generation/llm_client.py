"""
LLM Client wrapper with tool-calling mechanics.

Supports Groq (e.g. qwen/qwen3.8-27b or openai/gpt-oss-120b) and Gemini.
"""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..utils.logging import get_logger

logger = get_logger("generation.llm_client")

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None  # type: ignore


class LLMClient:
    """Provides chat completions and tool-calling loop capabilities."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.LLM_MODEL
        self._groq_client = None
        if settings.GROQ_API_KEY and AsyncGroq:
            self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Send messages and tool definitions to the LLM.
        Returns response structure: {"content": str | None, "tool_calls": list}
        """
        if not self._groq_client:
            raise EnvironmentError("GROQ_API_KEY is not configured or groq package not installed.")

        response = await self._groq_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )

        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return {
            "content": message.content,
            "tool_calls": tool_calls,
        }
