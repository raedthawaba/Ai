"""Phase 8.1 — Mock Provider: للاختبار والتطوير."""
from __future__ import annotations

import asyncio
import time
from typing import AsyncGenerator, List

from ..base import (
    BaseLLMProvider,
    LLMConfig,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)


class MockProvider(BaseLLMProvider):
    """
    مزود وهمي للاختبار والتطوير.

    يُرجع استجابات جاهزة بدون API خارجي،
    ويدعم streaming وهمياً.
    """

    MOCK_RESPONSES = [
        "الذكاء الاصطناعي يتطور بسرعة كبيرة في مجالات متعددة.",
        "نماذج اللغة الكبيرة أصبحت قادرة على فهم السياق بشكل أعمق.",
        "التعلم العميق يُمكّن النماذج من معالجة المعلومات المعقدة.",
        "هذه استجابة من Mock Provider للاختبار والتطوير.",
        "يمكن للذكاء الاصطناعي الآن معالجة النصوص العربية بكفاءة عالية.",
    ]

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._response_index = 0
        self._call_count = 0

    async def initialize(self) -> None:
        self._initialized = True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        await asyncio.sleep(0.05)  # محاكاة تأخير بسيط

        user_msg = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_msg = msg.content[:50]
                break

        response_text = (
            f"[Mock Response #{self._call_count + 1}] "
            f"استجابة على: '{user_msg}' — "
            + self.MOCK_RESPONSES[self._response_index % len(self.MOCK_RESPONSES)]
        )
        self._response_index += 1
        self._call_count += 1

        token_count = len(response_text.split())
        prompt_tokens = sum(len(m.content.split()) for m in request.messages)

        return LLMResponse(
            content=response_text,
            model=self.model_name,
            provider=self.provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=token_count,
            total_tokens=prompt_tokens + token_count,
            finish_reason="stop",
            request_id=request.request_id,
        )

    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        response = await self.complete(request)
        words = response.content.split()

        for i, word in enumerate(words):
            await asyncio.sleep(0.02)
            is_last = i == len(words) - 1
            yield LLMStreamChunk(
                delta=word + ("" if is_last else " "),
                finish_reason="stop" if is_last else None,
                index=i,
                model=self.model_name,
            )

    async def health_check(self) -> bool:
        try:
            from ..base import LLMMessage
            req = LLMRequest(
                messages=[LLMMessage(role="user", content="ping")],
                max_tokens=5,
            )
            response = await self.complete(req)
            return len(response.content) > 0
        except Exception:
            return False

    @property
    def call_count(self) -> int:
        return self._call_count
