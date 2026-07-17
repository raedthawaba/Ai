"""
Decision Engine v3 — محرك اتخاذ القرار المستقل والاستدلالي
===========================================================

يقرر:
- النموذج المناسب
- الأدوات المناسبة
- استخدام RAG أو لا
- استخدام أكثر من نموذج
- إعادة المحاولة
- إعادة التخطيط
- التوازي
- ترتيب التنفيذ

يعتمد على:
- جودة النماذج (من قاعدة البيانات التاريخية)
- الأداء (الكمون، معدل النجاح)
- التكلفة (tokens، API calls)
- السرعة (latency targets)
- التاريخ السابق (ما نجح من قبل)
- السياسات (Policy Engine)
- مستوى الثقة (confidence scores)

لا توجد قواعد ثابتة — كل قرار يعتمد على الاستدلال والبيانات.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from hajeen_platform.core.llm import LLMManager
from hajeen_platform.brain.goal_manager import Goal, IntentType, ComplexityLevel

logger = logging.getLogger(__name__)


class ResourceType(str, Enum):
    """أنواع الموارد المتاحة."""
    LOCAL_MODEL = "local_model"
    CLOUD_MODEL = "cloud_model"
    RAG = "rag"
    WEB_SEARCH = "web_search"
    TOOL = "tool"
    MULTI_MODEL = "multi_model"
    CACHE = "cache"


class RetryStrategy(str, Enum):
    """استراتيجيات إعادة المحاولة."""
    NO_RETRY = "no_retry"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    ADAPTIVE = "adaptive"


class ExecutionOrder(str, Enum):
    """ترتيب التنفيذ."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


@dataclass
class ModelCandidate:
    """مرشح نموذج مع درجاته."""
    model_id: str
    quality_score: float  # 0-1 (من قاعدة البيانات)
    performance_score: float  # 0-1 (الكمون، معدل النجاح)
    cost_score: float  # 0-1 (التكلفة النسبية)
    speed_score: float  # 0-1 (السرعة النسبية)
    historical_success_rate: float  # 0-1 (معدل النجاح السابق)
    confidence: float  # 0-1 (ثقتنا في هذا الخيار)
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceAllocation:
    """تخصيص الموارد لمهمة."""
    resource_id: str
    resource_type: ResourceType
    primary_model: str
    fallback_models: List[str]
    use_rag: bool
    use_web: bool
    use_multi_model: bool
    collaborating_models: List[str]
    max_retries: int
    retry_strategy: RetryStrategy
    execution_order: ExecutionOrder
    parallel_limit: int
    estimated_tokens: int
    estimated_cost_usd: float
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type.value,
            "primary_model": self.primary_model,
            "fallback_models": self.fallback_models,
            "use_rag": self.use_rag,
            "use_web": self.use_web,
            "use_multi_model": self.use_multi_model,
            "collaborating_models": self.collaborating_models,
            "max_retries": self.max_retries,
            "retry_strategy": self.retry_strategy.value,
            "execution_order": self.execution_order.value,
            "parallel_limit": self.parallel_limit,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
        }


@dataclass
class DecisionReasoning:
    """شرح تفصيلي للقرار."""
    decision_id: str
    goal_analysis: str
    model_candidates: List[ModelCandidate]
    selected_model: str
    selection_reasoning: str
    risk_assessment: str
    fallback_plan: str
    resource_constraints: List[str]
    optimization_opportunities: List[str]
    confidence_factors: Dict[str, float]
    overall_confidence: float


class DecisionEngineV3:
    """
    محرك اتخاذ القرار المستقل والاستدلالي v3.
    
    يستخدم:
    - LLM للاستدلال العميق
    - قاعدة بيانات الأداء التاريخية
    - Policy Engine للقيود
    - Reasoning Engine للتحليل المتقدم
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        performance_db: Optional[Any] = None,
        policy_engine: Optional[Any] = None,
        reasoning_engine: Optional[Any] = None,
    ) -> None:
        self.llm_manager = llm_manager
        self.performance_db = performance_db
        self.policy_engine = policy_engine
        self.reasoning_engine = reasoning_engine
        self._decisions_cache: Dict[str, ResourceAllocation] = {}
        self._decision_history: List[ResourceAllocation] = []
        logger.info("DecisionEngineV3: initialized")

    async def decide(
        self,
        task_id: str,
        goal: Goal,
        context: Optional[Dict[str, Any]] = None,
    ) -> ResourceAllocation:
        """
        اتخاذ قرار استدلالي عميق لمهمة.
        
        الخطوات:
        1. تحليل الهدف والسياق
        2. جمع المرشحين المحتملين
        3. تقييم كل مرشح
        4. اختيار الأفضل
        5. تخطيط الموارد والفشل
        6. بناء قرار نهائي
        """
        resource_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: تحليل الهدف والسياق ──────────────────────────
            goal_analysis = await self._analyze_goal_and_context(goal, context)
            
            # ── Step 2: جمع المرشحين المحتملين ──────────────────────
            candidates = await self._gather_model_candidates(goal, goal_analysis)
            
            # ── Step 3: تقييم كل مرشح ────────────────────────────────
            scored_candidates = await self._score_candidates(candidates, goal)
            
            # ── Step 4: اختيار النموذج الأساسي ──────────────────────
            primary_model, primary_reasoning = await self._select_primary_model(
                scored_candidates, goal
            )
            
            # ── Step 5: اختيار النماذج الاحتياطية ──────────────────
            fallback_models = await self._select_fallback_models(
                scored_candidates, primary_model, goal
            )
            
            # ── Step 6: اتخاذ قرارات تكتيكية ─────────────────────────
            use_rag = await self._decide_rag_usage(goal, primary_model)
            use_web = await self._decide_web_search_usage(goal)
            use_multi_model = await self._decide_multi_model_collaboration(goal, scored_candidates)
            collaborating = await self._select_collaborating_models(
                scored_candidates, primary_model, use_multi_model, goal
            ) if use_multi_model else []
            
            # ── Step 7: تخطيط إعادة المحاولة والفشل ──────────────────
            retry_strategy, max_retries = await self._plan_retry_strategy(goal)
            
            # ── Step 8: تخطيط ترتيب التنفيذ ──────────────────────────
            execution_order, parallel_limit = await self._plan_execution_order(
                goal, use_multi_model, collaborating
            )
            
            # ── Step 9: تقدير الموارد ────────────────────────────────
            estimated_tokens = await self._estimate_tokens(goal, primary_model)
            estimated_cost = await self._estimate_cost(goal, primary_model, estimated_tokens)
            
            # ── Step 10: حساب الثقة الكلية ────────────────────────────
            overall_confidence = await self._calculate_overall_confidence(
                scored_candidates, primary_model, goal
            )
            
            # ── Step 11: بناء شرح القرار ──────────────────────────────
            decision_reasoning = await self._build_decision_reasoning(
                resource_id, goal_analysis, scored_candidates, primary_model,
                primary_reasoning, use_rag, use_web, use_multi_model, fallback_models
            )
            
            # ── Step 12: بناء القرار النهائي ──────────────────────────
            allocation = ResourceAllocation(
                resource_id=resource_id,
                resource_type=self._determine_resource_type(
                    primary_model, use_rag, use_web, use_multi_model
                ),
                primary_model=primary_model,
                fallback_models=fallback_models,
                use_rag=use_rag,
                use_web=use_web,
                use_multi_model=use_multi_model,
                collaborating_models=collaborating,
                max_retries=max_retries,
                retry_strategy=retry_strategy,
                execution_order=execution_order,
                parallel_limit=parallel_limit,
                estimated_tokens=estimated_tokens,
                estimated_cost_usd=estimated_cost,
                confidence=overall_confidence,
                reasoning=decision_reasoning.selection_reasoning,
                metadata={
                    "goal_id": goal.goal_id,
                    "domain": goal.domain,
                    "intent": goal.intent,
                    "complexity": goal.complexity,
                    "decision_reasoning": decision_reasoning,
                },
            )
            
            # تخزين مؤقت
            self._decisions_cache[resource_id] = allocation
            self._decision_history.append(allocation)
            
            logger.info(
                "decision_engine_v3: decided task_id=%s model=%s confidence=%.3f tokens=%d cost=%.6f",
                task_id, primary_model, overall_confidence, estimated_tokens, estimated_cost
            )
            
            return allocation
        
        except Exception as e:
            logger.error("decision_engine_v3: error during decision: %s", e, exc_info=True)
            # استجابة احتياطية
            return ResourceAllocation(
                resource_id=resource_id,
                resource_type=ResourceType.CLOUD_MODEL,
                primary_model="openai/gpt-4o",
                fallback_models=[],
                use_rag=False,
                use_web=False,
                use_multi_model=False,
                collaborating_models=[],
                max_retries=1,
                retry_strategy=RetryStrategy.NO_RETRY,
                execution_order=ExecutionOrder.SEQUENTIAL,
                parallel_limit=1,
                estimated_tokens=2048,
                estimated_cost_usd=0.01,
                confidence=0.5,
                reasoning=f"فشل الاستدلال: {str(e)}",
                metadata={"error": str(e)},
            )

    async def _analyze_goal_and_context(
        self,
        goal: Goal,
        context: Optional[Dict[str, Any]],
    ) -> str:
        """تحليل الهدف والسياق."""
        try:
            context_str = json.dumps(context, ensure_ascii=False) if context else ""
            
            prompt = f"""حلّل الهدف والسياق التالي:

الهدف: {goal.final_objective}
النية: {goal.intent}
التعقيد: {goal.complexity}
المجال: {goal.domain}
المهام الفرعية: {', '.join(goal.sub_tasks)}

السياق: {context_str}

قدّم تحليلاً موجزاً يغطي:
1. ما هي المتطلبات الحقيقية
2. ما هي التحديات المحتملة
3. ما هي الموارد المطلوبة
4. ما هي القيود المحتملة"""
            
            analysis = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=500,
            )
            
            return analysis
        except Exception as e:
            logger.warning("decision_engine_v3: failed to analyze goal: %s", e)
            return "تحليل احتياطي: هدف عام"

    async def _gather_model_candidates(
        self,
        goal: Goal,
        goal_analysis: str,
    ) -> List[str]:
        """جمع المرشحين المحتملين."""
        candidates = []
        
        # المرشحون من قاعدة البيانات
        if self.performance_db:
            try:
                db_candidates = await self.performance_db.get_suitable_models_for(
                    intent=goal.intent,
                    domain=goal.domain,
                    complexity=goal.complexity,
                    limit=5,
                )
                candidates.extend(db_candidates)
            except Exception as e:
                logger.warning("decision_engine_v3: failed to get DB candidates: %s", e)
        
        # المرشحون الافتراضيون
        default_candidates = [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "qwen2.5-72b",
            "qwen2.5-7b",
            "ollama/llama3",
            "ollama/mistral",
        ]
        candidates.extend(default_candidates)
        
        # إزالة التكرارات
        candidates = list(dict.fromkeys(candidates))
        
        return candidates[:10]  # حد أقصى 10 مرشحين

    async def _score_candidates(
        self,
        candidates: List[str],
        goal: Goal,
    ) -> List[ModelCandidate]:
        """تقييم كل مرشح."""
        scored = []
        
        for model_id in candidates:
            try:
                # الحصول على بيانات الأداء
                quality = await self._get_model_quality(model_id)
                performance = await self._get_model_performance(model_id, goal)
                cost = await self._get_model_cost_score(model_id)
                speed = await self._get_model_speed_score(model_id)
                success_rate = await self._get_model_success_rate(model_id, goal)
                
                # حساب الثقة
                confidence = (quality + performance + success_rate) / 3
                
                # بناء المرشح
                candidate = ModelCandidate(
                    model_id=model_id,
                    quality_score=quality,
                    performance_score=performance,
                    cost_score=cost,
                    speed_score=speed,
                    historical_success_rate=success_rate,
                    confidence=confidence,
                    reasoning=f"جودة={quality:.2f}, أداء={performance:.2f}, نجاح={success_rate:.2f}",
                )
                scored.append(candidate)
            except Exception as e:
                logger.warning("decision_engine_v3: failed to score candidate %s: %s", model_id, e)
        
        # ترتيب حسب الثقة
        scored.sort(key=lambda c: c.confidence, reverse=True)
        return scored

    async def _select_primary_model(
        self,
        candidates: List[ModelCandidate],
        goal: Goal,
    ) -> Tuple[str, str]:
        """اختيار النموذج الأساسي."""
        if not candidates:
            return "openai/gpt-4o", "لا توجد مرشحين، استخدام الافتراضي"
        
        # اختيار الأفضل
        best = candidates[0]
        
        reasoning = (
            f"اختيار {best.model_id} "
            f"(جودة={best.quality_score:.2f}, "
            f"أداء={best.performance_score:.2f}, "
            f"نجاح سابق={best.historical_success_rate:.2f})"
        )
        
        return best.model_id, reasoning

    async def _select_fallback_models(
        self,
        candidates: List[ModelCandidate],
        primary_model: str,
        goal: Goal,
    ) -> List[str]:
        """اختيار النماذج الاحتياطية."""
        fallback = []
        
        # اختيار 2-3 نماذج احتياطية من المرشحين
        for candidate in candidates[1:]:
            if candidate.model_id != primary_model and len(fallback) < 3:
                fallback.append(candidate.model_id)
        
        return fallback

    async def _decide_rag_usage(self, goal: Goal, primary_model: str) -> bool:
        """تحديد ما إذا كان استخدام RAG مفيداً."""
        try:
            # RAG مفيد للمجالات التي تحتاج معرفة محدثة
            rag_beneficial_domains = ["rag", "research", "data", "general"]
            
            if goal.domain in rag_beneficial_domains:
                # استخدام LLM للقرار
                prompt = f"""هل يجب استخدام RAG (استرجاع المعرفة) للمهمة التالية؟

الهدف: {goal.final_objective}
المجال: {goal.domain}
النموذج: {primary_model}

أجب بـ 'نعم' أو 'لا' فقط مع شرح موجز."""
                
                response = await self.llm_manager.generate(
                    prompt=prompt,
                    model="gpt-4o-mini",
                    temperature=0.2,
                    max_tokens=50,
                )
                
                return "نعم" in response.lower()
        except Exception as e:
            logger.warning("decision_engine_v3: failed to decide RAG usage: %s", e)
        
        return False

    async def _decide_web_search_usage(self, goal: Goal) -> bool:
        """تحديد ما إذا كان البحث على الويب مفيداً."""
        try:
            web_beneficial_intents = [IntentType.RESEARCH, IntentType.QUESTION]
            
            if goal.intent in web_beneficial_intents:
                prompt = f"""هل يجب البحث على الإنترنت للمهمة التالية؟

الهدف: {goal.final_objective}
النية: {goal.intent}

أجب بـ 'نعم' أو 'لا' فقط."""
                
                response = await self.llm_manager.generate(
                    prompt=prompt,
                    model="gpt-4o-mini",
                    temperature=0.2,
                    max_tokens=20,
                )
                
                return "نعم" in response.lower()
        except Exception as e:
            logger.warning("decision_engine_v3: failed to decide web search usage: %s", e)
        
        return False

    async def _decide_multi_model_collaboration(
        self,
        goal: Goal,
        candidates: List[ModelCandidate],
    ) -> bool:
        """تحديد ما إذا كان التعاون متعدد النماذج مفيداً."""
        # التعاون مفيد للمهام المعقدة
        if goal.complexity in ["complex", "enterprise"]:
            # التحقق من توفر مرشحين متعددين
            if len(candidates) >= 2:
                return True
        
        return False

    async def _select_collaborating_models(
        self,
        candidates: List[ModelCandidate],
        primary_model: str,
        use_multi_model: bool,
        goal: Goal,
    ) -> List[str]:
        """اختيار النماذج المتعاونة."""
        if not use_multi_model or len(candidates) < 2:
            return []
        
        collaborating = []
        for candidate in candidates[1:]:
            if candidate.model_id != primary_model and len(collaborating) < 2:
                collaborating.append(candidate.model_id)
        
        return collaborating

    async def _plan_retry_strategy(
        self,
        goal: Goal,
    ) -> Tuple[RetryStrategy, int]:
        """تخطيط استراتيجية إعادة المحاولة."""
        # المهام المعقدة تحتاج إعادة محاولة
        if goal.complexity in ["complex", "enterprise"]:
            return RetryStrategy.ADAPTIVE, 3
        elif goal.complexity == "medium":
            return RetryStrategy.EXPONENTIAL_BACKOFF, 2
        else:
            return RetryStrategy.NO_RETRY, 1

    async def _plan_execution_order(
        self,
        goal: Goal,
        use_multi_model: bool,
        collaborating: List[str],
    ) -> Tuple[ExecutionOrder, int]:
        """تخطيط ترتيب التنفيذ."""
        if use_multi_model and len(collaborating) > 0:
            return ExecutionOrder.PARALLEL, len(collaborating) + 1
        elif goal.complexity in ["complex", "enterprise"]:
            return ExecutionOrder.HYBRID, 2
        else:
            return ExecutionOrder.SEQUENTIAL, 1

    async def _estimate_tokens(self, goal: Goal, primary_model: str) -> int:
        """تقدير عدد الرموز المطلوبة."""
        base_tokens = {
            "simple": 500,
            "medium": 1500,
            "complex": 4000,
            "enterprise": 8000,
        }
        
        tokens = base_tokens.get(goal.complexity, 1500)
        
        # تعديل بناءً على المجال
        domain_multipliers = {
            "code": 1.5,
            "rag": 1.3,
            "training": 2.0,
            "general": 1.0,
        }
        
        multiplier = domain_multipliers.get(goal.domain, 1.0)
        return int(tokens * multiplier)

    async def _estimate_cost(
        self,
        goal: Goal,
        primary_model: str,
        tokens: int,
    ) -> float:
        """تقدير التكلفة."""
        # أسعار تقريبية (بالدولار)
        model_rates = {
            "openai/gpt-4o": 0.005 / 1000,
            "openai/gpt-4o-mini": 0.00015 / 1000,
            "qwen2.5-72b": 0.001 / 1000,
            "qwen2.5-7b": 0.0001 / 1000,
            "ollama/llama3": 0.0,  # محلي
            "ollama/mistral": 0.0,  # محلي
        }
        
        rate = model_rates.get(primary_model, 0.001 / 1000)
        return tokens * rate

    async def _calculate_overall_confidence(
        self,
        candidates: List[ModelCandidate],
        primary_model: str,
        goal: Goal,
    ) -> float:
        """حساب الثقة الكلية."""
        if not candidates:
            return 0.5
        
        # الثقة من المرشح الأساسي
        primary_candidate = next(
            (c for c in candidates if c.model_id == primary_model),
            None
        )
        
        if primary_candidate:
            return primary_candidate.confidence
        
        return candidates[0].confidence if candidates else 0.5

    async def _build_decision_reasoning(
        self,
        resource_id: str,
        goal_analysis: str,
        candidates: List[ModelCandidate],
        primary_model: str,
        selection_reasoning: str,
        use_rag: bool,
        use_web: bool,
        use_multi_model: bool,
        fallback_models: List[str],
    ) -> DecisionReasoning:
        """بناء شرح تفصيلي للقرار."""
        risk_assessment = ""
        if use_multi_model:
            risk_assessment = "مخاطر منخفضة: تعاون متعدد النماذج يوفر تنويع"
        else:
            risk_assessment = f"مخاطر متوسطة: اعتماد على نموذج واحد ({primary_model})"
        
        fallback_plan = f"النماذج الاحتياطية: {', '.join(fallback_models)}"
        
        return DecisionReasoning(
            decision_id=resource_id,
            goal_analysis=goal_analysis,
            model_candidates=candidates[:3],
            selected_model=primary_model,
            selection_reasoning=selection_reasoning,
            risk_assessment=risk_assessment,
            fallback_plan=fallback_plan,
            resource_constraints=[],
            optimization_opportunities=[
                "استخدام caching للنتائج المتكررة",
                "تحسين token budget",
            ],
            confidence_factors={
                "model_quality": candidates[0].quality_score if candidates else 0.5,
                "historical_success": candidates[0].historical_success_rate if candidates else 0.5,
                "performance": candidates[0].performance_score if candidates else 0.5,
            },
            overall_confidence=candidates[0].confidence if candidates else 0.5,
        )

    def _determine_resource_type(
        self,
        model: str,
        use_rag: bool,
        use_web: bool,
        use_multi: bool,
    ) -> ResourceType:
        """تحديد نوع المورد."""
        if use_multi:
            return ResourceType.MULTI_MODEL
        if use_web:
            return ResourceType.WEB_SEARCH
        if use_rag:
            return ResourceType.RAG
        if "openai" in model or "cloud" in model:
            return ResourceType.CLOUD_MODEL
        return ResourceType.LOCAL_MODEL

    async def _get_model_quality(self, model_id: str) -> float:
        """الحصول على درجة جودة النموذج."""
        if self.performance_db:
            try:
                stats = await self.performance_db.get_model_statistics(model_id)
                return stats.get("quality_score", 0.7)
            except:
                pass
        
        # قيم افتراضية
        default_quality = {
            "openai/gpt-4o": 0.95,
            "openai/gpt-4o-mini": 0.85,
            "qwen2.5-72b": 0.90,
            "qwen2.5-7b": 0.80,
            "ollama/llama3": 0.75,
        }
        return default_quality.get(model_id, 0.7)

    async def _get_model_performance(self, model_id: str, goal: Goal) -> float:
        """الحصول على درجة الأداء."""
        if self.performance_db:
            try:
                stats = await self.performance_db.get_model_statistics(
                    model_id, domain=goal.domain
                )
                return stats.get("performance_score", 0.7)
            except:
                pass
        
        return 0.7

    async def _get_model_cost_score(self, model_id: str) -> float:
        """الحصول على درجة التكلفة (أقل = أفضل)."""
        # درجة عكسية: النماذج المحلية أفضل (1.0)
        if "ollama" in model_id or "local" in model_id:
            return 1.0
        if "mini" in model_id:
            return 0.8
        if "gpt-4o" in model_id:
            return 0.5
        return 0.7

    async def _get_model_speed_score(self, model_id: str) -> float:
        """الحصول على درجة السرعة."""
        # النماذج المحلية أسرع عادة
        if "ollama" in model_id:
            return 0.9
        if "mini" in model_id:
            return 0.85
        if "gpt-4o" in model_id:
            return 0.7
        return 0.7

    async def _get_model_success_rate(self, model_id: str, goal: Goal) -> float:
        """الحصول على معدل النجاح السابق."""
        if self.performance_db:
            try:
                stats = await self.performance_db.get_model_statistics(
                    model_id, domain=goal.domain, intent=goal.intent
                )
                return stats.get("success_rate", 0.7)
            except:
                pass
        
        return 0.7

    def get_decision(self, resource_id: str) -> Optional[ResourceAllocation]:
        """الحصول على قرار محفوظ."""
        return self._decisions_cache.get(resource_id)

    def get_recent_decisions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """آخر القرارات."""
        recent = self._decision_history[-limit:]
        return [d.to_dict() for d in recent]

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات القرارات."""
        if not self._decision_history:
            return {"total_decisions": 0}
        
        total = len(self._decision_history)
        multi_model_count = sum(1 for d in self._decision_history if d.use_multi_model)
        rag_count = sum(1 for d in self._decision_history if d.use_rag)
        web_count = sum(1 for d in self._decision_history if d.use_web)
        
        avg_confidence = sum(d.confidence for d in self._decision_history) / total
        avg_tokens = sum(d.estimated_tokens for d in self._decision_history) / total
        total_cost = sum(d.estimated_cost_usd for d in self._decision_history)
        
        return {
            "total_decisions": total,
            "multi_model_decisions": multi_model_count,
            "rag_decisions": rag_count,
            "web_decisions": web_count,
            "avg_confidence": round(avg_confidence, 3),
            "avg_tokens": int(avg_tokens),
            "total_cost_usd": round(total_cost, 6),
        }


# Singleton
_decision_engine_v3: Optional[DecisionEngineV3] = None


def get_decision_engine_v3(
    llm_manager: Optional[LLMManager] = None,
    performance_db: Optional[Any] = None,
    policy_engine: Optional[Any] = None,
    reasoning_engine: Optional[Any] = None,
) -> DecisionEngineV3:
    """الحصول على instance من DecisionEngineV3."""
    global _decision_engine_v3
    if _decision_engine_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _decision_engine_v3 = DecisionEngineV3(
            llm_manager, performance_db, policy_engine, reasoning_engine
        )
    return _decision_engine_v3
