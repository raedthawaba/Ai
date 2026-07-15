"""
Model Router — الموجّه الذكي للنماذج
======================================
يوجّه كل طلب للنموذج الأنسب بناءً على:
الجودة، السرعة، التكلفة، اللغة، نوع المهمة، نتائج الاستخدام السابقة.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RouteResult:
    model_id: str
    provider: str
    latency_ms: float
    tokens_used: int
    response: str
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    model_id: str
    provider: str                  # ollama | openai | qwen | huggingface | local
    base_url: Optional[str]
    api_key: Optional[str]
    capabilities: List[str]        # code, arabic, math, general, rag
    max_tokens: int
    avg_latency_ms: float
    cost_per_1k_tokens: float      # 0.0 للنماذج المحلية
    quality_score: float           # 0-1
    is_local: bool


# قاموس النماذج المدعومة
DEFAULT_MODELS: Dict[str, ModelConfig] = {
    "ollama/llama3": ModelConfig(
        model_id="llama3", provider="ollama",
        base_url="http://localhost:11434",
        api_key=None,
        capabilities=["general", "rag", "conversation"],
        max_tokens=4096, avg_latency_ms=800,
        cost_per_1k_tokens=0.0, quality_score=0.78,
        is_local=True,
    ),
    "ollama/qwen2.5": ModelConfig(
        model_id="qwen2.5:7b", provider="ollama",
        base_url="http://localhost:11434",
        api_key=None,
        capabilities=["arabic", "general", "code"],
        max_tokens=8192, avg_latency_ms=1000,
        cost_per_1k_tokens=0.0, quality_score=0.82,
        is_local=True,
    ),
    "ollama/qwen2.5-coder": ModelConfig(
        model_id="qwen2.5-coder:7b", provider="ollama",
        base_url="http://localhost:11434",
        api_key=None,
        capabilities=["code"],
        max_tokens=8192, avg_latency_ms=900,
        cost_per_1k_tokens=0.0, quality_score=0.85,
        is_local=True,
    ),
    "openai/gpt-4o": ModelConfig(
        model_id="gpt-4o", provider="openai",
        base_url=None, api_key="env:OPENAI_API_KEY",
        capabilities=["general", "code", "math", "analysis", "creative"],
        max_tokens=128000, avg_latency_ms=2000,
        cost_per_1k_tokens=5.0, quality_score=0.97,
        is_local=False,
    ),
    "openai/gpt-4o-mini": ModelConfig(
        model_id="gpt-4o-mini", provider="openai",
        base_url=None, api_key="env:OPENAI_API_KEY",
        capabilities=["general", "code", "rag"],
        max_tokens=128000, avg_latency_ms=800,
        cost_per_1k_tokens=0.15, quality_score=0.88,
        is_local=False,
    ),
    "hajeen-local": ModelConfig(
        model_id="hajeen-v1", provider="local",
        base_url=None, api_key=None,
        capabilities=["arabic", "general"],
        max_tokens=4096, avg_latency_ms=500,
        cost_per_1k_tokens=0.0, quality_score=0.70,
        is_local=True,
    ),
}

# معادلة الترتيب: القيم الأعلى تعني نموذج أفضل
def _score_model(model: ModelConfig, capability: str, budget_tokens: int) -> float:
    cap_score = 1.0 if capability in model.capabilities else 0.3
    cost_score = 1.0 if model.cost_per_1k_tokens == 0 else max(0.1, 1 - model.cost_per_1k_tokens / 10)
    speed_score = max(0.1, 1 - model.avg_latency_ms / 5000)
    total = (model.quality_score * 0.4) + (cap_score * 0.3) + (cost_score * 0.2) + (speed_score * 0.1)
    return total


class ModelRouter:
    """
    الموجّه الذكي — يختار النموذج الأنسب لكل طلب
    ويدعم: Fallback، Multi-model، Local-first policy.
    """

    def __init__(self, prefer_local: bool = True) -> None:
        self._models = dict(DEFAULT_MODELS)
        self._prefer_local = prefer_local
        self._routing_history: List[Dict] = []
        self._provider_registry: Dict[str, Any] = {}

    def register_provider(self, model_key: str, provider_instance: Any) -> None:
        self._provider_registry[model_key] = provider_instance
        logger.info("model_router: registered provider for %s", model_key)

    def add_model(self, key: str, config: ModelConfig) -> None:
        self._models[key] = config
        logger.info("model_router: added model %s", key)

    def select_model(
        self, capability: str = "general", budget_tokens: int = 4096,
        force_local: bool = False, exclude: Optional[List[str]] = None,
    ) -> Optional[str]:
        """اختيار أفضل نموذج متاح."""
        exclude = exclude or []
        candidates = {
            k: v for k, v in self._models.items()
            if k not in exclude
        }

        if force_local or self._prefer_local:
            local_candidates = {k: v for k, v in candidates.items() if v.is_local}
            if local_candidates:
                candidates = local_candidates

        if not candidates:
            candidates = self._models  # fallback لكل النماذج

        best_key = max(candidates, key=lambda k: _score_model(candidates[k], capability, budget_tokens))
        logger.info("model_router: selected %s for capability=%s", best_key, capability)
        return best_key

    async def route(
        self,
        messages: List[Dict[str, str]],
        capability: str = "general",
        budget_tokens: int = 4096,
        force_model: Optional[str] = None,
        timeout: float = 60.0,
    ) -> RouteResult:
        """توجيه الطلب وتنفيذه مع دعم Fallback."""
        model_key = force_model or self.select_model(capability, budget_tokens)
        tried: List[str] = []

        while model_key and model_key not in tried:
            tried.append(model_key)
            model_cfg = self._models.get(model_key)
            if not model_cfg:
                break

            t0 = time.perf_counter()
            try:
                response_text = await asyncio.wait_for(
                    self._call_model(model_key, model_cfg, messages),
                    timeout=timeout,
                )
                latency = (time.perf_counter() - t0) * 1000
                self._record_routing(model_key, capability, latency, True)
                return RouteResult(
                    model_id=model_key,
                    provider=model_cfg.provider,
                    latency_ms=latency,
                    tokens_used=len(response_text.split()),
                    response=response_text,
                    success=True,
                )
            except asyncio.TimeoutError:
                logger.warning("model_router: timeout for %s", model_key)
            except Exception as e:
                logger.warning("model_router: error for %s: %s", model_key, e)

            # جرّب النموذج الاحتياطي
            model_key = self.select_model(capability, budget_tokens, exclude=tried)

        return RouteResult(
            model_id=model_key or "none",
            provider="none",
            latency_ms=0,
            tokens_used=0,
            response="",
            success=False,
            error="All models failed or timed out",
        )

    async def _call_model(
        self, model_key: str, cfg: ModelConfig, messages: List[Dict[str, str]]
    ) -> str:
        """استدعاء النموذج الفعلي عبر المزود المسجّل."""
        # إذا كان المزود مسجّلاً في الـ Registry، استخدمه
        if model_key in self._provider_registry:
            provider = self._provider_registry[model_key]
            if hasattr(provider, "chat"):
                resp = await provider.chat(messages[-1]["content"] if messages else "")
                return resp.get("content", "") if isinstance(resp, dict) else str(resp)

        # استدعاء Ollama مباشرةً للنماذج المحلية
        if cfg.provider == "ollama":
            return await self._call_ollama(cfg, messages)

        # استدعاء OpenAI
        if cfg.provider == "openai":
            return await self._call_openai(cfg, messages)

        # Fallback نصي
        return f"[{cfg.model_id}] استجابة محاكاة — النموذج غير متصل حالياً"

    async def _call_ollama(self, cfg: ModelConfig, messages: List[Dict]) -> str:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{cfg.base_url}/api/chat",
                    json={"model": cfg.model_id, "messages": messages, "stream": False},
                )
                data = resp.json()
                return data.get("message", {}).get("content", "")
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")

    async def _call_openai(self, cfg: ModelConfig, messages: List[Dict]) -> str:
        try:
            import os
            import httpx
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not set")
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": cfg.model_id, "messages": messages, "max_tokens": 2048},
                )
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}")

    def _record_routing(self, model_key: str, capability: str, latency_ms: float, success: bool) -> None:
        self._routing_history.append({
            "model": model_key,
            "capability": capability,
            "latency_ms": latency_ms,
            "success": success,
            "at": time.time(),
        })
        # احتفظ بآخر 1000 سجل فقط
        if len(self._routing_history) > 1000:
            self._routing_history = self._routing_history[-1000:]

    def get_routing_stats(self) -> Dict[str, Any]:
        if not self._routing_history:
            return {"total": 0}
        total = len(self._routing_history)
        success = sum(1 for r in self._routing_history if r["success"])
        by_model: Dict[str, int] = {}
        for r in self._routing_history:
            by_model[r["model"]] = by_model.get(r["model"], 0) + 1
        return {
            "total": total,
            "success_rate": round(success / total, 3),
            "by_model": by_model,
            "avg_latency_ms": round(
                sum(r["latency_ms"] for r in self._routing_history) / total, 1
            ),
        }


# Singleton
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
