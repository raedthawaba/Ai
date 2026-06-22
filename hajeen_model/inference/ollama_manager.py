"""
Ollama Manager — إدارة تثبيت وتشغيل النماذج عبر Ollama.

يوفر:
- فحص تثبيت Ollama
- تحميل النماذج
- إدارة النماذج المحلية
- التحقق من حالة الخادم
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
HAJEEN_MODEL = "qwen2.5:1.5b"


class OllamaManager:
    """مدير Ollama للنماذج المحلية."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url

    async def is_running(self) -> bool:
        """هل خادم Ollama يعمل؟"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[Dict]:
        """قائمة النماذج المثبتة."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                return r.json().get("models", [])
        except Exception as e:
            logger.error("list_models error: %s", e)
            return []

    async def is_model_available(self, model_name: str = HAJEEN_MODEL) -> bool:
        """هل النموذج مثبت؟"""
        models = await self.list_models()
        return any(m.get("name", "").startswith(model_name.split(":")[0]) for m in models)

    async def pull_model(self, model_name: str = HAJEEN_MODEL) -> bool:
        """تحميل نموذج من Ollama."""
        logger.info("Pulling model: %s", model_name)
        try:
            async with httpx.AsyncClient(timeout=600.0) as c:
                async with c.stream("POST", f"{self.base_url}/api/pull",
                                    json={"name": model_name}) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            import json
                            try:
                                data = json.loads(line)
                                status = data.get("status", "")
                                if "error" in data:
                                    logger.error("Pull error: %s", data["error"])
                                    return False
                                if status:
                                    logger.info("Pull: %s", status)
                            except Exception:
                                pass
            return True
        except Exception as e:
            logger.error("pull_model error: %s", e)
            return False

    async def delete_model(self, model_name: str) -> bool:
        """حذف نموذج محلي."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.delete(f"{self.base_url}/api/delete",
                                   json={"name": model_name})
                return r.status_code == 200
        except Exception as e:
            logger.error("delete_model error: %s", e)
            return False

    async def get_model_info(self, model_name: str) -> Optional[Dict]:
        """معلومات نموذج."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(f"{self.base_url}/api/show",
                                 json={"name": model_name})
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.error("get_model_info error: %s", e)
        return None

    async def status_report(self) -> Dict:
        """تقرير شامل عن حالة Ollama."""
        running = await self.is_running()
        models = await self.list_models() if running else []
        hajeen_available = any(
            m.get("name", "").startswith("qwen2.5") for m in models
        )
        return {
            "ollama_running": running,
            "ollama_url": self.base_url,
            "installed_models": [m.get("name") for m in models],
            "hajeen_model_available": hajeen_available,
            "recommended_action": (
                "جاهز للاستخدام ✓" if hajeen_available
                else "شغّل: ollama pull qwen2.5:1.5b" if running
                else "شغّل Ollama أولاً: ollama serve"
            ),
        }


_manager: Optional[OllamaManager] = None


def get_ollama_manager() -> OllamaManager:
    global _manager
    if _manager is None:
        _manager = OllamaManager()
    return _manager
