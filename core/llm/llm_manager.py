"""Phase 8.1 — LLM Manager: إدارة مزودي النماذج مع نظام Fallback."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional

from .base import (
    BaseLLMProvider,
    LLMConfig,
    LLMError,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)
from .config import LLMSettings
from .provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)

_manager_instance: Optional["LLMManager"] = None


class LLMManager:
    """
    مدير مركزي لمزودي LLM مع:
    - Provider fallback system
    - Dynamic provider switching
    - Async inference
    - Token streaming
    - Health monitoring
    """

    def __init__(
        self,
        primary_provider: Optional[str] = None,
        fallback_providers: Optional[List[str]] = None,
        settings: Optional[LLMSettings] = None,
    ):
        self.settings = settings or LLMSettings.from_env()
        self._primary_name = primary_provider or self.settings.provider
        self._fallback_names = fallback_providers or []
        self._providers: Dict[str, BaseLLMProvider] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """تهيئة المدير وتسجيل المزودين الافتراضيين."""
        if self._initialized:
            return

        ProviderRegistry.auto_register_defaults()

        # تهيئة المزود الرئيسي
        await self._ensure_provider(self._primary_name)

        # تهيئة مزودي الـ fallback
        for name in self._fallback_names:
            try:
                await self._ensure_provider(name)
            except Exception as e:
                logger.warning("Fallback provider '%s' unavailable: %s", name, e)

        self._initialized = True
        logger.info(
            "LLM Manager initialized: primary=%s, fallbacks=%s",
            self._primary_name,
            self._fallback_names,
        )

    async def _ensure_provider(self, name: str) -> BaseLLMProvider:
        """التأكد من وجود مزود وتهيئته."""
        if name not in self._providers:
            config = self.settings.to_llm_config()
            config.provider = name
            provider = ProviderRegistry.create(name, config)
            await provider.initialize()
            self._providers[name] = provider
        return self._providers[name]

    @property
    def primary_provider(self) -> BaseLLMProvider:
        if self._primary_name not in self._providers:
            raise LLMError("Manager not initialized. Call initialize() first.")
        return self._providers[self._primary_name]

    async def complete(
        self,
        request: LLMRequest,
        provider_name: Optional[str] = None,
    ) -> LLMResponse:
        """
        تنفيذ inference مع fallback system.

        يحاول المزود الرئيسي أولاً، ثم المزودين البدلاء عند الفشل.
        """
        if not self._initialized:
            await self.initialize()

        # فرض استخدام المزود المحلي 'hajeen' فقط كما طلب المستخدم
        # مع الإبقاء على منطق المزودين الآخرين مسجلاً ولكن غير مفعل
        pname = "hajeen"
        
        try:
            provider = await self._ensure_provider(pname)
            logger.debug("Forcing local provider: %s", pname)
            response = await provider.complete_with_retry(request)
            return response
        except Exception as e:
            logger.error("Local provider 'hajeen' failed: %s", e)
            raise LLMError(f"Local provider 'hajeen' failed: {e}")

    async def stream(
        self,
        request: LLMRequest,
        provider_name: Optional[str] = None,
    ) -> AsyncGenerator[LLMStreamChunk, None]:
        """تنفيذ streaming inference."""
        if not self._initialized:
            await self.initialize()

        # فرض استخدام المزود المحلي 'hajeen' في الـ streaming
        pname = "hajeen"
        provider = await self._ensure_provider(pname)
        request.stream = True

        async for chunk in provider.stream(request):
            yield chunk

    async def health_check_all(self) -> Dict[str, bool]:
        """فحص صحة جميع المزودين."""
        if not self._initialized:
            await self.initialize()

        results = {}
        tasks = {
            name: provider.health_check()
            for name, provider in self._providers.items()
        }
        for name, task in tasks.items():
            try:
                results[name] = await asyncio.wait_for(task, timeout=10.0)
            except Exception:
                results[name] = False
        return results

    async def switch_primary(self, new_provider: str) -> None:
        """تغيير المزود الرئيسي بدون إعادة تشغيل النظام."""
        await self._ensure_provider(new_provider)
        old = self._primary_name
        self._primary_name = new_provider
        logger.info("Switched primary provider: %s → %s", old, new_provider)

    def get_provider_names(self) -> List[str]:
        return list(self._providers.keys())

    async def get_available_models(self) -> Dict[str, str]:
        """قائمة بالنماذج المتاحة لكل مزود."""
        if not self._initialized:
            await self.initialize()
        return {
            name: provider.model_name
            for name, provider in self._providers.items()
        }


def get_llm_manager() -> LLMManager:
    """Singleton instance لـ LLMManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LLMManager()
    return _manager_instance


def set_llm_manager(manager: LLMManager) -> None:
    """تعيين instance مخصص (للاختبار)."""
    global _manager_instance
    _manager_instance = manager
