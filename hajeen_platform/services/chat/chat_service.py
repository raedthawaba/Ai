"""Phase 8.6 — Chat Service: خدمة الدردشة الرئيسية مع RAG."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.llm.base import LLMMessage
from core.llm.llm_manager import LLMManager, get_llm_manager
from core.inference_engine.engine import InferenceEngine, get_inference_engine
from core.inference_engine.stream_handler import StreamEvent
from services.prompts.prompt_builder import PromptBuilder
from services.memory.session_manager import SessionManager, get_session_manager
from brain.memory.unified_interface import get_unified_memory
from .chat_session import ChatSession, TurnResult
from .citation_injector import CitationInjector
from .moderation_layer import ModerationLayer
from .response_postprocessor import ResponsePostprocessor

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
    خدمة الدردشة الرئيسية.

    Pipeline:
    1. Moderation فحص المدخلات
    2. Session management
    3. RAG retrieval (اختياري)
    4. Prompt building
    5. LLM inference
    6. Response postprocessing
    7. Citation injection
    8. Memory storage
    """

    def __init__(
        self,
        inference_engine: Optional[InferenceEngine] = None,
        session_manager: Optional[SessionManager] = None,
        rag_pipeline: Optional[Any] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        moderation: Optional[ModerationLayer] = None,
        postprocessor: Optional[ResponsePostprocessor] = None,
        citation_injector: Optional[CitationInjector] = None,
    ):
        self._engine = inference_engine
        self._sessions = session_manager
        self._rag = rag_pipeline
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.moderation = moderation or ModerationLayer()
        self.postprocessor = postprocessor or ResponsePostprocessor()
        self.citation_injector = citation_injector or CitationInjector()
        self._initialized = False

    @property
    def engine(self) -> InferenceEngine:
        if self._engine is None:
            self._engine = get_inference_engine()
        return self._engine

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
        await self.engine.initialize()
        self._initialized = True
        logger.info("ChatService initialized")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        تنفيذ محادثة كاملة.
        """
        if not self._initialized:
            await self.initialize()

        t_start = time.perf_counter()
        turn_id = str(uuid.uuid4())

        # 1. Moderation
        mod_result = self.moderation.check_input(request.message)
        if not mod_result.passed:
            return ChatResponse(
                content=(
                    "عذراً، لا يمكنني معالجة هذا الطلب. "
                    f"السبب: {mod_result.reason}"
                    if request.language == "ar"
                    else f"Sorry, I cannot process this request. Reason: {mod_result.reason}"
                ),
                session_id=request.session_id or str(uuid.uuid4()),
                turn_id=turn_id,
                model="moderation",
                provider="moderation",
                sources=[],
                latency_ms=0.0,
                tokens_used=0,
                language=request.language,
            )

        # 2. Session management
        session_id = request.session_id or str(uuid.uuid4())
        chat_session = self.sessions.get_or_create(
            session_id=session_id,
            system_prompt=request.system_prompt,
        )

        # 3. RAG retrieval
        sources: List[Dict[str, Any]] = []
        context_chunks: List[Dict[str, Any]] = []

        if request.use_rag and self._rag:
            try:
                from services.rag.rag_pipeline import RAGRequest
                rag_req = RAGRequest(
                    query=request.message,
                    top_k=request.top_k,
                    language=request.language,
                )
                rag_result = await self._rag.run(rag_req)
                sources = rag_result.formatted.citations or []
                context_chunks = [
                    {"text": src.get("text", ""), "title": src.get("title", ""),
                     "url": src.get("url", ""), "score": src.get("score", 0.0)}
                    for src in sources
                ]
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e)

        # 4. Prompt building
        if context_chunks:
            built_prompt = self.prompt_builder.build_rag_prompt(
                question=request.message,
                context_chunks=context_chunks,
                language=request.language,
                history=chat_session.memory.get_messages(include_system=False),
            )
        else:
            history = chat_session.get_context_messages()
            built_prompt = self.prompt_builder.build_chat_prompt(
                user_message=request.message,
                history=[m for m in history if m.role != "system"],
                language=request.language,
                system_prompt_name=request.system_prompt,
            )

        # 5. LLM Inference
        messages_dicts = [
            {"role": m.role, "content": m.content}
            for m in built_prompt.messages
        ]

        processed = await self.engine.infer(
            messages=messages_dicts,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            session_id=session_id,
        )

        # 6. Post-processing
        postprocessed = self.postprocessor.process(
            processed.cleaned_content,
            language=request.language,
        )

        # 7. Citation injection
        final_content = self.citation_injector.inject(
            postprocessed.content,
            sources,
        )

        # 8. Output moderation
        out_mod = self.moderation.check_output(final_content)
        if not out_mod.passed:
            final_content = (
                "عذراً، حدث خطأ في معالجة الاستجابة."
                if request.language == "ar"
                else "Sorry, there was an error processing the response."
            )

        latency_ms = (time.perf_counter() - t_start) * 1000

        # 9. Store in memory (Unified — writes to both MemoryFabric + SessionManager)
        turn_result = TurnResult(
            turn_id=turn_id,
            user_message=request.message,
            assistant_response=final_content,
            sources=sources,
            latency_ms=latency_ms,
            tokens_used=processed.total_tokens,
            model=processed.model,
            provider=processed.provider,
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
            "Chat turn: session=%s lang=%s tokens=%d latency=%.1fms",
            session_id, request.language, processed.total_tokens, latency_ms,
        )

        return ChatResponse(
            content=final_content,
            session_id=session_id,
            turn_id=turn_id,
            model=processed.model,
            provider=processed.provider,
            sources=self.citation_injector.format_citations_for_api(sources),
            latency_ms=latency_ms,
            tokens_used=processed.total_tokens,
            language=request.language,
        )

    async def stream_chat(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamEvent, None]:
        """محادثة مع streaming."""
        if not self._initialized:
            await self.initialize()

        # Moderation check
        mod_result = self.moderation.check_input(request.message)
        if not mod_result.passed:
            from core.inference_engine.stream_handler import StreamEvent
            yield StreamEvent(
                event_type="error",
                data=f"Blocked: {mod_result.reason}",
            )
            return

        session_id = request.session_id or str(uuid.uuid4())
        stream_id = str(uuid.uuid4())

        # Build messages
        messages = [
            {"role": "user", "content": request.message}
        ]

        async for event in self.engine.stream_infer(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            session_id=session_id,
            stream_id=stream_id,
        ):
            yield event

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
