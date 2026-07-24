"""Phase 8.6 — Chat Service: خدمة الدردشة الرئيسية مع RAG (Adapter for HajeenBrainV3)."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from brain.brain_v3 import HajeenBrainV3, BrainRequest, BrainResponse, get_brain_v3
from core.inference_engine.stream_handler import StreamEvent
from services.memory.session_manager import SessionManager, get_session_manager
from brain.memory.unified_interface import get_unified_memory
from .chat_session import ChatSession, TurnResult
from .citation_injector import CitationInjector

logger = logging.getLogger(__name__)


@dataclass
class ChatRequest:
    """طلب محادثة."""
    message: str
    session_id: Optional[str] = None
    language: str = "ar"
    use_rag: bool = True
    stream: bool = False
    top_k: int = 5
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """استجابة المحادثة."""
    content: str
    session_id: str
    turn_id: str
    model: str
    provider: str
    sources: List[Dict[str, Any]]
    latency_ms: float
    tokens_used: int
    language: str = "ar"
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "response": self.content,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "model": self.model,
            "provider": self.provider,
            "sources": self.sources,
            "latency_ms": round(self.latency_ms, 2),
            "tokens_used": self.tokens_used,
            "language": self.language,
        }


class ChatService:
    """
    خدمة الدردشة الرئيسية (Adapter).
    
    تم تحويل هذه الخدمة لتكون مجرد محول (Adapter) يمرر الطلبات إلى HajeenBrainV3.
    جميع عمليات الـ Moderation, RAG, Prompt Building, Inference, Postprocessing
    تتم الآن داخل العقل المركزي (Brain).
    """

    def __init__(
        self,
        brain: Optional[HajeenBrainV3] = None,
        session_manager: Optional[SessionManager] = None,
        rag_pipeline: Optional[Any] = None,
        citation_injector: Optional[CitationInjector] = None,
    ):
        self._brain = brain
        self._sessions = session_manager
        self._rag = rag_pipeline
        self.citation_injector = citation_injector or CitationInjector()
        self._initialized = False

    @property
    def sessions(self) -> SessionManager:
        if self._sessions is None:
            self._sessions = get_session_manager()
        return self._sessions

    @property
    def unified_memory(self):
        """الوصول للذاكرة الموحّدة (UnifiedMemoryInterface)."""
        return get_unified_memory()

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._brain = self._brain or await get_brain_v3()
        self._initialized = True
        logger.info("ChatService initialized as adapter for HajeenBrainV3")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        تنفيذ محادثة كاملة عبر HajeenBrainV3.
        """
        if not self._initialized:
            await self.initialize()

        t_start = time.perf_counter()
        turn_id = str(uuid.uuid4())
        session_id = request.session_id or str(uuid.uuid4())

        # 1. Prepare BrainRequest
        brain_request = BrainRequest(
            request_id=turn_id,
            user_message=request.message,
            session_id=session_id,
            context={
                "language": request.language,
                "use_rag": request.use_rag,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "model": request.model,
                "top_k": request.top_k,
                "system_prompt": request.system_prompt,
            },
            stream=False,
            max_tokens=request.max_tokens or 2048,
            temperature=request.temperature or 0.7,
            force_model=request.model,
        )

        # 2. Process through Brain
        brain_response: BrainResponse = await self._brain.process(brain_request)

        # 3. Extract results
        final_content = brain_response.content
        model_used = brain_response.model_used
        provider_used = brain_response.policy_decision # Placeholder, could be extracted from trace
        
        # Extract sources if RAG was used (assuming Brain puts them in trace execution)
        sources = brain_response.trace.execution.get("rag_sources", [])
        
        tokens_used = brain_response.trace.tokens_used
        latency_ms = brain_response.trace.total_latency_ms

        # 4. Store in legacy SessionManager for compatibility
        chat_session = self.sessions.get_or_create(
            session_id=session_id,
            system_prompt=request.system_prompt,
        )
        
        turn_result = TurnResult(
            turn_id=turn_id,
            user_message=request.message,
            assistant_response=final_content,
            sources=sources,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            model=model_used,
            provider=provider_used,
        )
        chat_session.add_turn(turn_result)

        # Also write to UnifiedMemoryInterface for cross-system sync
        try:
            import asyncio
            asyncio.create_task(
                self.unified_memory.add_message(
                    session_id=session_id,
                    role="user",
                    content=request.message,
                    metadata={"turn_id": turn_id, "type": "user"}
                )
            )
            asyncio.create_task(
                self.unified_memory.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=final_content,
                    metadata={"turn_id": turn_id, "type": "assistant", "sources": sources}
                )
            )
        except Exception as e:
            logger.debug("UnifiedMemoryInterface write skipped: %s", e)

        logger.info(
            "Chat turn (via Brain): session=%s lang=%s tokens=%d latency=%.1fms",
            session_id, request.language, tokens_used, latency_ms,
        )

        return ChatResponse(
            content=final_content,
            session_id=session_id,
            turn_id=turn_id,
            model=model_used,
            provider=provider_used,
            sources=self.citation_injector.format_citations_for_api(sources),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            language=request.language,
        )

    async def stream_chat(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamEvent, None]:
        """محادثة مع streaming عبر HajeenBrainV3."""
        if not self._initialized:
            await self.initialize()

        session_id = request.session_id or str(uuid.uuid4())
        stream_id = str(uuid.uuid4())

        brain_request = BrainRequest(
            request_id=stream_id,
            user_message=request.message,
            session_id=session_id,
            context={
                "language": request.language,
                "use_rag": request.use_rag,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "model": request.model,
                "top_k": request.top_k,
                "system_prompt": request.system_prompt,
                "stream": True,
            },
            stream=True,
            max_tokens=request.max_tokens or 2048,
            temperature=request.temperature or 0.7,
            force_model=request.model,
        )

        try:
            async for chunk in self._brain.stream(brain_request):
                # Parse SSE format from Brain stream
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield StreamEvent(event_type="done", data="")
                        break
                    
                    try:
                        import json
                        # Brain stream yields dict strings like {'content': '...'}
                        # We need to safely evaluate or parse them
                        import ast
                        data_dict = ast.literal_eval(data_str)
                        if "content" in data_dict:
                            yield StreamEvent(event_type="content", data=data_dict["content"])
                        elif "brain_decision" in data_dict:
                            yield StreamEvent(event_type="meta", data=data_dict["brain_decision"])
                    except Exception as e:
                        logger.debug("Failed to parse stream chunk: %s", e)
                        # Fallback: just yield the raw string if it's not a dict
                        yield StreamEvent(event_type="content", data=data_str)
        except Exception as e:
            yield StreamEvent(event_type="error", data=str(e))

    def set_rag_pipeline(self, rag_pipeline: Any) -> None:
        """تعيين RAG pipeline."""
        self._rag = rag_pipeline

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """معلومات جلسة محادثة."""
        session = self.sessions.get_session(session_id)
        if not session:
            return None
        return session.to_dict()


# Singleton
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
