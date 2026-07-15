"""
Multi-Model Collaboration — تعاون عدة نماذج
=============================================
يسمح لعدة نماذج بالتعاون لإنتاج إجابة أفضل من أي نموذج منفرد.
استراتيجيات الدمج: Voting, Ensemble, Chain, Debate.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CollaborationStrategy(str, Enum):
    CHAIN = "chain"         # النماذج تتسلسل — كل نموذج يحسّن إجابة السابق
    ENSEMBLE = "ensemble"   # كل نموذج يجيب مستقلاً ثم تُدمج الإجابات
    DEBATE = "debate"       # النماذج تتجادل ثم تتوصل لإجابة مشتركة
    VOTING = "voting"       # الإجابة الأكثر تكراراً تفوز
    EXPERT = "expert"       # كل نموذج خبير في جانب محدد


@dataclass
class ModelResponse:
    model_id: str
    content: str
    latency_ms: float
    tokens: int
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CollaborationResult:
    strategy: CollaborationStrategy
    models_used: List[str]
    individual_responses: List[ModelResponse]
    final_answer: str
    confidence: float
    total_latency_ms: float
    total_tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "models_used": self.models_used,
            "final_answer": self.final_answer,
            "confidence": self.confidence,
            "total_latency_ms": self.total_latency_ms,
            "total_tokens": self.total_tokens,
            "individual_count": len(self.individual_responses),
        }


class MultiModelCollaborator:
    """
    ينسّق تعاون عدة نماذج لإنتاج إجابة أفضل.

    مثال:
        Hajeen → Qwen → OpenAI → Ollama → دمج النتائج
    """

    def __init__(self, model_router=None) -> None:
        self._router = model_router
        self._history: List[CollaborationResult] = []

    async def collaborate(
        self,
        query: str,
        models: List[str],
        strategy: CollaborationStrategy = CollaborationStrategy.CHAIN,
        context: Optional[Dict] = None,
    ) -> CollaborationResult:
        """تنسيق التعاون بين النماذج."""
        t0 = time.perf_counter()
        context = context or {}

        if strategy == CollaborationStrategy.CHAIN:
            result = await self._chain_strategy(query, models, context)
        elif strategy == CollaborationStrategy.ENSEMBLE:
            result = await self._ensemble_strategy(query, models, context)
        elif strategy == CollaborationStrategy.DEBATE:
            result = await self._debate_strategy(query, models, context)
        elif strategy == CollaborationStrategy.VOTING:
            result = await self._voting_strategy(query, models, context)
        else:
            result = await self._expert_strategy(query, models, context)

        total_latency = (time.perf_counter() - t0) * 1000
        result.total_latency_ms = total_latency
        self._history.append(result)
        logger.info(
            "multi_model: strategy=%s models=%d latency=%.1fms",
            strategy, len(models), total_latency
        )
        return result

    async def _chain_strategy(
        self, query: str, models: List[str], context: Dict
    ) -> CollaborationResult:
        """كل نموذج يحسّن إجابة النموذج السابق."""
        responses: List[ModelResponse] = []
        current_input = query

        for i, model_key in enumerate(models):
            prompt = current_input if i == 0 else (
                f"حسّن الإجابة التالية على السؤال '{query}':\n\n{current_input}\n\n"
                "اجعلها أكثر دقة وشمولاً:"
            )
            resp = await self._call_model(model_key, prompt)
            responses.append(resp)
            current_input = resp.content  # ناتج النموذج الحالي هو مدخل التالي

        final = responses[-1].content if responses else ""
        return CollaborationResult(
            strategy=CollaborationStrategy.CHAIN,
            models_used=models,
            individual_responses=responses,
            final_answer=final,
            confidence=0.85,
            total_latency_ms=0,
            total_tokens=sum(r.tokens for r in responses),
        )

    async def _ensemble_strategy(
        self, query: str, models: List[str], context: Dict
    ) -> CollaborationResult:
        """جميع النماذج تجيب بالتوازي ثم تُدمج الإجابات."""
        tasks = [self._call_model(m, query) for m in models]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in responses if isinstance(r, ModelResponse) and r.content]

        if not valid:
            final = "لم يتمكن أي نموذج من الإجابة."
        elif len(valid) == 1:
            final = valid[0].content
        else:
            # دمج الإجابات
            combined = "\n\n---\n\n".join(
                f"[{r.model_id}]:\n{r.content}" for r in valid
            )
            # في الحقيقة نريد نموذج يدمجها؛ نستخدم أفضل نموذج متاح
            merge_prompt = (
                f"السؤال: {query}\n\nلديك الإجابات التالية من عدة نماذج:\n\n{combined}\n\n"
                "اكتب إجابة واحدة موحدة تجمع أفضل ما في هذه الإجابات:"
            )
            merge_resp = await self._call_model(models[0], merge_prompt)
            final = merge_resp.content if merge_resp.content else combined

        return CollaborationResult(
            strategy=CollaborationStrategy.ENSEMBLE,
            models_used=models,
            individual_responses=valid,
            final_answer=final,
            confidence=min(0.95, 0.7 + len(valid) * 0.05),
            total_latency_ms=0,
            total_tokens=sum(r.tokens for r in valid),
        )

    async def _debate_strategy(
        self, query: str, models: List[str], context: Dict
    ) -> CollaborationResult:
        """النماذج تتجادل وتتوصل لإجابة مشتركة (جولتان)."""
        responses: List[ModelResponse] = []

        # الجولة الأولى
        initial_tasks = [self._call_model(m, query) for m in models[:2]]
        initial = await asyncio.gather(*initial_tasks, return_exceptions=True)
        valid_initial = [r for r in initial if isinstance(r, ModelResponse) and r.content]
        responses.extend(valid_initial)

        # الجولة الثانية — كل نموذج يرد على الآخر
        if len(valid_initial) >= 2:
            debate_prompt = (
                f"السؤال: {query}\n\n"
                f"قال النموذج الأول: {valid_initial[0].content}\n\n"
                f"قال النموذج الثاني: {valid_initial[1].content}\n\n"
                "ما هو التوليف الأفضل لكلتا الإجابتين؟"
            )
            final_resp = await self._call_model(models[0], debate_prompt)
            responses.append(final_resp)
            final = final_resp.content
        elif valid_initial:
            final = valid_initial[0].content
        else:
            final = ""

        return CollaborationResult(
            strategy=CollaborationStrategy.DEBATE,
            models_used=models[:2],
            individual_responses=responses,
            final_answer=final,
            confidence=0.88,
            total_latency_ms=0,
            total_tokens=sum(r.tokens for r in responses),
        )

    async def _voting_strategy(
        self, query: str, models: List[str], context: Dict
    ) -> CollaborationResult:
        """الإجابة الأكثر تشابهاً بين النماذج تفوز."""
        tasks = [self._call_model(m, query) for m in models]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        valid = [r for r in responses if isinstance(r, ModelResponse) and r.content]

        # اختر أطول إجابة كتصويت افتراضي
        final = max(valid, key=lambda r: len(r.content)).content if valid else ""

        return CollaborationResult(
            strategy=CollaborationStrategy.VOTING,
            models_used=models,
            individual_responses=valid,
            final_answer=final,
            confidence=0.80,
            total_latency_ms=0,
            total_tokens=sum(r.tokens for r in valid),
        )

    async def _expert_strategy(
        self, query: str, models: List[str], context: Dict
    ) -> CollaborationResult:
        """كل نموذج خبير في جانب — تقسيم العمل."""
        aspects = [
            "الجانب التقني والتقني",
            "الجانب العملي والتطبيقي",
            "الجانب الإبداعي والمبتكر",
        ]
        responses: List[ModelResponse] = []
        for i, model_key in enumerate(models[:len(aspects)]):
            aspect = aspects[i] if i < len(aspects) else "الجانب العام"
            prompt = f"أجب من منظور {aspect} فقط على السؤال: {query}"
            resp = await self._call_model(model_key, prompt)
            responses.append(resp)

        combined = "\n\n".join(
            f"**{aspects[i] if i < len(aspects) else 'عام'}:**\n{r.content}"
            for i, r in enumerate(responses)
        )
        return CollaborationResult(
            strategy=CollaborationStrategy.EXPERT,
            models_used=models[:len(aspects)],
            individual_responses=responses,
            final_answer=combined,
            confidence=0.87,
            total_latency_ms=0,
            total_tokens=sum(r.tokens for r in responses),
        )

    async def _call_model(self, model_key: str, prompt: str) -> ModelResponse:
        """استدعاء نموذج عبر Model Router."""
        t0 = time.perf_counter()
        try:
            if self._router:
                result = await self._router.route(
                    messages=[{"role": "user", "content": prompt}],
                    force_model=model_key,
                )
                return ModelResponse(
                    model_id=model_key,
                    content=result.response,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                    tokens=result.tokens_used,
                )
        except Exception as e:
            logger.warning("multi_model: error calling %s: %s", model_key, e)

        # Fallback نصي
        return ModelResponse(
            model_id=model_key,
            content=f"[{model_key}] غير متاح حالياً",
            latency_ms=(time.perf_counter() - t0) * 1000,
            tokens=0,
            confidence=0.0,
        )

    def get_stats(self) -> Dict[str, Any]:
        if not self._history:
            return {"total": 0}
        return {
            "total": len(self._history),
            "by_strategy": {
                s.value: sum(1 for r in self._history if r.strategy == s)
                for s in CollaborationStrategy
            },
            "avg_models_per_call": round(
                sum(len(r.models_used) for r in self._history) / len(self._history), 1
            ),
        }


# Singleton
_collaborator: Optional[MultiModelCollaborator] = None


def get_multi_model_collaborator(model_router=None) -> MultiModelCollaborator:
    global _collaborator
    if _collaborator is None:
        _collaborator = MultiModelCollaborator(model_router=model_router)
    return _collaborator
