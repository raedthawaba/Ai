"""Phase 8.6 — AI Chat Service."""
from .chat_service import ChatService, ChatRequest, ChatResponse
from .chat_session import ChatSession as ChatSessionService
from .response_postprocessor import ResponsePostprocessor
from .citation_injector import CitationInjector
from .moderation_layer import ModerationLayer, ModerationResult

__all__ = [
    "ChatService", "ChatRequest", "ChatResponse",
    "ChatSessionService",
    "ResponsePostprocessor",
    "CitationInjector",
    "ModerationLayer", "ModerationResult",
]
