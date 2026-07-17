"""
Model Router v3 — موجّه النماذج الذكي
====================================

يوجّه الطلبات إلى النماذج المناسبة بناءً على:
- المهمة والمجال
- اللغة والحجم
- حجم السياق
- الأداء الحقيقي
- التكلفة
- الجودة
- معدل النجاح
- الإمكانيات المطلوبة

يتعلم من النتائج السابقة ويحسّن الاختيارات بمرور الوقت.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from hajeen_platform.core.llm import LLMManager
from hajeen_platform.brain.goal_manager import Goal

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """استراتيجيات التوجيه."""
    QUALITY_FIRST = "quality_first"          # الجودة أولاً
    COST_OPTIMIZED = "cost_optimized"        # التكلفة أولاً
    SPEED_OPTIMIZED = "speed_optimized"      # السرعة أولاً
    BALANCED = "balanced"                    # متوازن
    ADAPTIVE = "adaptive"                    # تكيفي (يتعلم)


@dataclass
class RoutingDecision:
    """قرار التوجيه."""
    routing_id: str
    primary_model: str
    fallback_models: List[str]
    strategy_used: RoutingStrategy
    quality_score: float
    cost_score: float
    speed_score: float
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "routing_id": self.routing_id,
            "primary_model": self.primary_model,
            "fallback_models": self.fallback_models,
            "strategy_used": self.strategy_used.value,
            "quality_score": round(self.quality_score, 3),
            "cost_score": round(self.cost_score, 3),
            "speed_score": round(self.speed_score, 3),
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "created_at": self.created_at,
        }


@dataclass
class RoutingResult:
    """نتيجة التوجيه والتنفيذ."""
    routing_id: str
    model_used: str
    response: str
    tokens_used: int
    latency_ms: float
    quality_score: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class ModelRouterV3:
    """
    موجّه النماذج الذكي v3.
    
    يستخدم:
    - LLM للقرارات المعقدة
    - قاعدة بيانات الأداء
    - استراتيجيات توجيه متعددة
    - التعلم من النتائج السابقة
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        performance_db: Optional[Any] = None,
    ) -> None:
        self.llm_manager = llm_manager
        self.performance_db = performance_db
        self._routing_cache: Dict[str, RoutingDecision] = {}
        self._routing_history: List[RoutingDecision] = []
        self._model_stats: Dict[str, Dict[str, Any]] = {}
        logger.info("ModelRouterV3: initialized")

    async def route(
        self,
        messages: List[Dict[str, str]],
        goal: Goal,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
        context: Optional[Dict[str, Any]] = None,
    ) -> RoutingResult:
        """
        توجيه الطلب إلى النموذج المناسب.
        
        الخطوات:
        1. تحليل الطلب
        2. جمع بيانات الأداء
        3. تقييم المرشحين
        4. اختيار النموذج الأساسي
        5. تنفيذ الطلب
        6. تسجيل النتيجة
        """
        routing_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        
        try:
            # ── Step 1: اتخاذ قرار التوجيه ──────────────────────────
            routing_decision = await self._make_routing_decision(
                goal, strategy, context
            )
            
            # ── Step 2: تنفيذ الطلب ────────────────────────────────
            response, tokens_used = await self._execute_with_model(
                messages, routing_decision.primary_model
            )
            
            latency_ms = (time.perf_counter() - t0) * 1000
            
            # ── Step 3: تقييم النتيجة ──────────────────────────────
            quality_score = await self._evaluate_response_quality(response, goal)
            
            # ── Step 4: تسجيل النتيجة ──────────────────────────────
            result = RoutingResult(
                routing_id=routing_id,
                model_used=routing_decision.primary_model,
                response=response,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                quality_score=quality_score,
                success=bool(response),
                metadata={
                    "routing_decision": routing_decision.to_dict(),
                    "goal": goal.to_dict(),
                },
            )
            
            # تحديث إحصائيات النموذج
            await self._update_model_stats(
                routing_decision.primary_model,
                latency_ms,
                tokens_used,
                quality_score,
                True,
            )
            
            logger.info(
                "model_router_v3: routed to %s latency=%.1f tokens=%d quality=%.3f",
                routing_decision.primary_model, latency_ms, tokens_used, quality_score
            )
            
            return result
        
        except Exception as e:
            logger.error("model_router_v3: error during routing: %s", e, exc_info=True)
            
            latency_ms = (time.perf_counter() - t0) * 1000
            
            return RoutingResult(
                routing_id=routing_id,
                model_used="fallback",
                response="",
                tokens_used=0,
                latency_ms=latency_ms,
                quality_score=0.0,
                success=False,
                error=str(e),
                metadata={"goal": goal.to_dict()},
            )

    async def _make_routing_decision(
        self,
        goal: Goal,
        strategy: RoutingStrategy,
        context: Optional[Dict[str, Any]],
    ) -> RoutingDecision:
        """اتخاذ قرار التوجيه."""
        routing_id = str(uuid.uuid4())
        
        try:
            # جمع المرشحين
            candidates = await self._gather_candidates(goal)
            
            # تقييم المرشحين
            scored = await self._score_candidates(candidates, goal, strategy)
            
            if not scored:
                # استجابة احتياطية
                return RoutingDecision(
                    routing_id=routing_id,
                    primary_model="openai/gpt-4o",
                    fallback_models=[],
                    strategy_used=strategy,
                    quality_score=0.5,
                    cost_score=0.5,
                    speed_score=0.5,
                    confidence=0.5,
                    reasoning="لا توجد مرشحين، استخدام الافتراضي",
                )
            
            # اختيار النموذج الأساسي
            primary = scored[0]
            fallback = [c["model_id"] for c in scored[1:3]]
            
            reasoning = (
                f"اختيار {primary['model_id']} "
                f"(جودة={primary['quality']:.2f}, "
                f"تكلفة={primary['cost']:.2f}, "
                f"سرعة={primary['speed']:.2f})"
            )
            
            decision = RoutingDecision(
                routing_id=routing_id,
                primary_model=primary["model_id"],
                fallback_models=fallback,
                strategy_used=strategy,
                quality_score=primary["quality"],
                cost_score=primary["cost"],
                speed_score=primary["speed"],
                confidence=primary["confidence"],
                reasoning=reasoning,
                metadata={"candidates": scored[:3]},
            )
            
            self._routing_cache[routing_id] = decision
            self._routing_history.append(decision)
            
            return decision
        
        except Exception as e:
            logger.warning("model_router_v3: failed to make routing decision: %s", e)
            
            return RoutingDecision(
                routing_id=routing_id,
                primary_model="openai/gpt-4o",
                fallback_models=[],
                strategy_used=strategy,
                quality_score=0.5,
                cost_score=0.5,
                speed_score=0.5,
                confidence=0.3,
                reasoning=f"فشل اتخاذ القرار: {str(e)}",
            )

    async def _gather_candidates(self, goal: Goal) -> List[str]:
        """جمع المرشحين المحتملين."""
        candidates = []
        
        # المرشحون من قاعدة البيانات
        if self.performance_db:
            try:
                db_candidates = await self.performance_db.get_suitable_models_for(
                    domain=goal.domain,
                    limit=5,
                )
                candidates.extend(db_candidates)
            except:
                pass
        
        # المرشحون الافتراضيون
        default = [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "qwen2.5-72b",
            "qwen2.5-7b",
            "ollama/llama3",
        ]
        candidates.extend(default)
        
        # إزالة التكرارات
        candidates = list(dict.fromkeys(candidates))
        
        return candidates[:10]

    async def _score_candidates(
        self,
        candidates: List[str],
        goal: Goal,
        strategy: RoutingStrategy,
    ) -> List[Dict[str, Any]]:
        """تقييم المرشحين حسب الاستراتيجية."""
        scored = []
        
        for model_id in candidates:
            try:
                quality = await self._get_model_quality(model_id, goal)
                cost = await self._get_model_cost(model_id)
                speed = await self._get_model_speed(model_id)
                
                # حساب درجة مركبة حسب الاستراتيجية
                if strategy == RoutingStrategy.QUALITY_FIRST:
                    composite = quality * 0.7 + speed * 0.2 + (1 - cost) * 0.1
                elif strategy == RoutingStrategy.COST_OPTIMIZED:
                    composite = (1 - cost) * 0.7 + quality * 0.2 + speed * 0.1
                elif strategy == RoutingStrategy.SPEED_OPTIMIZED:
                    composite = speed * 0.7 + quality * 0.2 + (1 - cost) * 0.1
                else:  # BALANCED or ADAPTIVE
                    composite = quality * 0.4 + speed * 0.3 + (1 - cost) * 0.3
                
                scored.append({
                    "model_id": model_id,
                    "quality": quality,
                    "cost": cost,
                    "speed": speed,
                    "confidence": composite,
                })
            except Exception as e:
                logger.warning("model_router_v3: failed to score %s: %s", model_id, e)
        
        # ترتيب حسب الدرجة المركبة
        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored

    async def _execute_with_model(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
    ) -> tuple[str, int]:
        """تنفيذ الطلب مع النموذج المختار."""
        try:
            # استخراج النموذج الفعلي
            if "/" in model_id:
                provider, model = model_id.split("/", 1)
            else:
                provider = "openai"
                model = model_id
            
            # تنفيذ الطلب
            if provider == "openai":
                response = await self.llm_manager.generate(
                    messages=messages,
                    model=model,
                    temperature=0.7,
                    max_tokens=2048,
                )
                # تقدير الرموز
                tokens = len(str(messages)) // 4 + 500
            else:
                # نماذج أخرى
                response = await self.llm_manager.generate(
                    messages=messages,
                    model=model_id,
                    temperature=0.7,
                    max_tokens=2048,
                )
                tokens = len(str(messages)) // 4 + 500
            
            return response, tokens
        
        except Exception as e:
            logger.error("model_router_v3: failed to execute with %s: %s", model_id, e)
            raise

    async def _evaluate_response_quality(self, response: str, goal: Goal) -> float:
        """تقييم جودة الاستجابة."""
        if not response:
            return 0.0
        
        score = 0.5
        
        # الطول
        if len(response) > 100:
            score += 0.1
        if len(response) > 500:
            score += 0.1
        
        # البنية
        if any(c in response for c in [".", "،", "؟", "\n"]):
            score += 0.1
        
        # الكلمات
        if len(response.split()) > 30:
            score += 0.1
        
        # عدم وجود أخطاء
        if "[DONE]" not in response and "error" not in response.lower():
            score += 0.1
        
        return min(1.0, score)

    async def _update_model_stats(
        self,
        model_id: str,
        latency_ms: float,
        tokens_used: int,
        quality_score: float,
        success: bool,
    ) -> None:
        """تحديث إحصائيات النموذج."""
        if model_id not in self._model_stats:
            self._model_stats[model_id] = {
                "total_calls": 0,
                "successful_calls": 0,
                "total_latency": 0.0,
                "total_tokens": 0,
                "total_quality": 0.0,
                "avg_latency": 0.0,
                "avg_quality": 0.0,
                "success_rate": 0.0,
            }
        
        stats = self._model_stats[model_id]
        stats["total_calls"] += 1
        if success:
            stats["successful_calls"] += 1
        stats["total_latency"] += latency_ms
        stats["total_tokens"] += tokens_used
        stats["total_quality"] += quality_score
        
        # حساب المتوسطات
        stats["avg_latency"] = stats["total_latency"] / stats["total_calls"]
        stats["avg_quality"] = stats["total_quality"] / stats["total_calls"]
        stats["success_rate"] = stats["successful_calls"] / stats["total_calls"]

    async def _get_model_quality(self, model_id: str, goal: Goal) -> float:
        """الحصول على درجة جودة النموذج."""
        if model_id in self._model_stats:
            return self._model_stats[model_id]["avg_quality"]
        
        # قيم افتراضية
        defaults = {
            "openai/gpt-4o": 0.95,
            "openai/gpt-4o-mini": 0.85,
            "qwen2.5-72b": 0.90,
            "qwen2.5-7b": 0.80,
            "ollama/llama3": 0.75,
        }
        return defaults.get(model_id, 0.7)

    async def _get_model_cost(self, model_id: str) -> float:
        """الحصول على درجة التكلفة (0-1، أقل = أفضل)."""
        if "ollama" in model_id or "local" in model_id:
            return 0.0  # مجاني
        if "mini" in model_id:
            return 0.2
        if "7b" in model_id:
            return 0.3
        if "72b" in model_id:
            return 0.5
        if "gpt-4o" in model_id:
            return 0.7
        return 0.5

    async def _get_model_speed(self, model_id: str) -> float:
        """الحصول على درجة السرعة (0-1، أعلى = أسرع)."""
        if model_id in self._model_stats:
            # حساب السرعة من الكمون
            avg_latency = self._model_stats[model_id]["avg_latency"]
            # تحويل الكمون إلى درجة (أقل كمون = درجة أعلى)
            return max(0.0, 1.0 - (avg_latency / 5000))
        
        # قيم افتراضية
        if "ollama" in model_id:
            return 0.9
        if "mini" in model_id:
            return 0.85
        if "7b" in model_id:
            return 0.8
        if "gpt-4o" in model_id:
            return 0.7
        return 0.7

    def get_routing_decision(self, routing_id: str) -> Optional[RoutingDecision]:
        """الحصول على قرار توجيه محفوظ."""
        return self._routing_cache.get(routing_id)

    def get_recent_routings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """آخر قرارات التوجيه."""
        recent = self._routing_history[-limit:]
        return [r.to_dict() for r in recent]

    def get_model_statistics(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """إحصائيات النماذج."""
        if model_id:
            return self._model_stats.get(model_id, {})
        
        return {
            "total_models": len(self._model_stats),
            "models": self._model_stats,
        }

    def get_routing_stats(self) -> Dict[str, Any]:
        """إحصائيات التوجيه العامة."""
        if not self._routing_history:
            return {"total_routings": 0}
        
        total = len(self._routing_history)
        
        # توزيع النماذج
        model_distribution = {}
        for routing in self._routing_history:
            model = routing.primary_model
            model_distribution[model] = model_distribution.get(model, 0) + 1
        
        # متوسط الثقة
        avg_confidence = sum(r.confidence for r in self._routing_history) / total
        
        return {
            "total_routings": total,
            "model_distribution": model_distribution,
            "avg_confidence": round(avg_confidence, 3),
            "model_stats": self._model_stats,
        }


# Singleton
_model_router_v3: Optional[ModelRouterV3] = None


def get_model_router_v3(
    llm_manager: Optional[LLMManager] = None,
    performance_db: Optional[Any] = None,
) -> ModelRouterV3:
    """الحصول على instance من ModelRouterV3."""
    global _model_router_v3
    if _model_router_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _model_router_v3 = ModelRouterV3(llm_manager, performance_db)
    return _model_router_v3
