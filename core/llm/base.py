"""Phase 8.1 — BaseLLMProvider: الواجهة المجردة لجميع مزودي النماذج."""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional


@dataclass
class LLMConfig:
    """إعدادات مزود النموذج."""
    provider: str = "mock"
    model: str = "mock-model"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.95
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    stream: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    """رسالة واحدة في المحادثة."""
    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMRequest:
    """طلب inference."""
    messages: List[LLMMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_messages_list(self) -> List[Dict[str, str]]:
        return [m.to_dict() for m in self.messages]


@dataclass
class LLMResponse:
    """استجابة inference كاملة."""
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "latency_ms": round(self.latency_ms, 2),
            "finish_reason": self.finish_reason,
        }


@dataclass
class LLMStreamChunk:
    """قطعة من streaming response."""
    delta: str
    finish_reason: Optional[str] = None
    index: int = 0
    model: Optional[str] = None


class LLMError(Exception):
    """خطأ عام في LLM."""
    pass


class LLMTimeoutError(LLMError):
    """انتهت مهلة الطلب."""
    pass


class LLMProviderError(LLMError):
    """خطأ من مزود النموذج."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class BaseLLMProvider(ABC):
    """
    الواجهة المجردة لجميع مزودي النماذج اللغوية.

    يجب أن يُنفّذ كل مزود:
    - complete()  — inference متزامن
    - stream()    — streaming async generator
    - health_check() — فحص صحة المزود
    """

    def __init__(self, config: LLMConfig):
        self.config = config
        self._initialized = False

    @property
    def provider_name(self) -> str:
        return self.config.provider

    @property
    def model_name(self) -> str:
        return self.config.model

    async def initialize(self) -> None:
        """تهيئة المزود (اختياري)."""
        self._initialized = True

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """تنفيذ inference وإرجاع استجابة كاملة."""
        ...

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncGenerator[LLMStreamChunk, None]:
        """تنفيذ streaming inference."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """فحص صحة المزود."""
        ...

    async def complete_with_retry(self, request: LLMRequest) -> LLMResponse:
        """
        تنفيذ inference مع retry logic و timeout handling.
        """
        last_error: Optional[Exception] = None
        for attempt in range(self.config.max_retries):
            try:
                t0 = time.perf_counter()
                response = await asyncio.wait_for(
                    self.complete(request),
                    timeout=self.config.timeout,
                )
                response.latency_ms = (time.perf_counter() - t0) * 1000
                return response
            except asyncio.TimeoutError:
                last_error = LLMTimeoutError(
                    f"Provider '{self.provider_name}' timed out after "
                    f"{self.config.timeout}s (attempt {attempt + 1}/{self.config.max_retries})"
                )
            except LLMProviderError as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
            except Exception as e:
                last_error = LLMError(f"Unexpected error: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))

        raise last_error or LLMError("Unknown error after retries")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name} model={self.model_name}>"
