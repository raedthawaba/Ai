"""
Self Reflection — التقييم الذاتي بعد كل تنفيذ
================================================
بعد كل تنفيذ، يقيّم النظام نفسه:
- هل كانت الخطة جيدة؟
- هل يوجد مسار أفضل؟
- هل استُخدم النموذج الصحيح؟
- هل يمكن تقليل التكلفة؟
- هل يمكن زيادة الجودة؟
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from hajeen_platform.monitoring.metrics.prometheus_metrics import (
    hajeen_reflection_latency_seconds,
    hajeen_reflection_reports_total,
    hajeen_reflection_score_overall,
    track_latency,
)

from ..decision_engine import DecisionEngine, get_decision_engine
from ..metrics.model_performance_db import ModelPerformanceDB, get_performance_db
from ..model_router import ModelRouter, get_model_router
from ..policy.policy_engine import PolicyEngine, get_policy_engine

logger = logging.getLogger(__name__)


@dataclass
class ReflectionReport:
    """تقرير التقييم الذاتي لتنفيذ واحد."""
    report_id: str
    task_id: str
    goal_id: str
    was_plan_good: bool
    better_path_exists: bool
    correct_model_used: bool
    cost_can_be_reduced: bool
    quality_can_increase: bool
    plan_score: float            # 0-1
    efficiency_score: float      # 0-1
    quality_score: float         # 0-1
    overall_score: float         # 0-1
    lessons_learned: List[str]
    recommendations: List[str]
    actual_latency_ms: float
    actual_tokens_used: int
    estimated_tokens: int
    model_used: str
    better_model_suggestion: Optional[str]
    cost_saving_suggestion: Optional[str]
    reflected_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "task_id": self.task_id,
            "goal_id": self.goal_id,
            "was_plan_good": self.was_plan_good,
            "better_path_exists": self.better_path_exists,
            "correct_model_used": self.correct_model_used,
            "cost_can_be_reduced": self.cost_can_be_reduced,
            "quality_can_increase": self.quality_can_increase,
            "plan_score": self.plan_score,
            "efficiency_score": self.efficiency_score,
            "quality_score": self.quality_score,
            "overall_score": self.overall_score,
            "lessons_learned": self.lessons_learned,
            "recommendations": self.recommendations,
            "model_used": self.model_used,
            "better_model_suggestion": self.better_model_suggestion,
            "reflected_at": self.reflected_at,
        }


class SelfReflection:
    """
    محرك التقييم الذاتي.
    يُشغَّل بعد كل تنفيذ لاستخلاص الدروس وتحسين القرارات المستقبلية.
    """

    # حدود الجودة
    GOOD_LATENCY_MS = 3000       # أقل من 3 ثوانٍ = جيد
    TOKEN_EFFICIENCY_RATIO = 0.7  # 70% من التقدير = كفاءة جيدة

    def __init__(self, storage_path: str = "storage_data/brain/reflections") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._reports: List[ReflectionReport] = []
        self._lessons_db: List[str] = []  # دروس مجمّعة
        self._decision_engine: Optional[DecisionEngine] = None
        self._model_router: Optional[ModelRouter] = None
        self._policy_engine: Optional[PolicyEngine] = None
        self._model_performance_db: Optional[ModelPerformanceDB] = None

    async def initialize(self) -> None:
        if self._decision_engine is None:
            self._decision_engine = await get_decision_engine()
        if self._model_router is None:
            self._model_router = get_model_router()
        if self._policy_engine is None:
            self._policy_engine = get_policy_engine()
        if self._model_performance_db is None:
            self._model_performance_db = get_performance_db()

    async def reflect_async(
        self,
        task_id: str,
        goal_id: str,
        model_used: str,
        actual_latency_ms: float,
        actual_tokens: int,
        estimated_tokens: int,
        response_quality: float,  # 0-1 من تقييم خارجي
        plan_steps: int,
        actual_steps: int,
        context: Optional[Dict] = None,
    ) -> str:
        """يرسل مهمة التقييم الذاتي إلى Celery worker."""
        from hajeen_platform.workers.async_tasks import reflection_task
        logger.info(f"Dispatching self-reflection for task {task_id} to Celery.")
        celery_result = reflection_task.delay(
            task_id=task_id,
            goal_id=goal_id,
            model_used=model_used,
            actual_latency_ms=actual_latency_ms,
            actual_tokens=actual_tokens,
            estimated_tokens=estimated_tokens,
            response_quality=response_quality,
            plan_steps=plan_steps,
            actual_steps=actual_steps,
            context=context
        )
        return celery_result.id

    async def reflect(
        self,
        task_id: str,
        goal_id: str,
        model_used: str,
        actual_latency_ms: float,
        actual_tokens: int,
        estimated_tokens: int,
        response_quality: float,  # 0-1 من تقييم خارجي
        plan_steps: int,
        actual_steps: int,
        context: Optional[Dict] = None,
    ) -> ReflectionReport:
        """تنفيذ التقييم الذاتي."""
        context = context or {}

        # تقييم الخطة
        plan_adherence = min(1.0, actual_steps / max(plan_steps, 1))
        was_plan_good = plan_adherence >= 0.8 and actual_latency_ms < self.GOOD_LATENCY_MS * 2

        # تقييم النموذج
        correct_model = actual_latency_ms < self.GOOD_LATENCY_MS and response_quality >= 0.7

        # تقييم التكلفة
        token_ratio = actual_tokens / max(estimated_tokens, 1)
        cost_can_reduce = token_ratio > 1.3  # استُخدم أكثر من المتوقع بـ 30%

        # تقييم الجودة
        quality_can_increase = response_quality < 0.85

        # حساب النقاط
        plan_score = min(1.0, plan_adherence * 0.6 + (1 - min(actual_latency_ms / 10000, 1)) * 0.4)
        efficiency_score = min(1.0, max(0, 1 - abs(token_ratio - 1) * 0.5))
        overall = (plan_score * 0.3 + efficiency_score * 0.3 + response_quality * 0.4)

        # الدروس والتوصيات
        lessons = await self._generate_lessons(
            was_plan_good, correct_model, cost_can_reduce, quality_can_increase,
            actual_latency_ms, token_ratio, model_used, response_quality
        )
        recommendations = await self._generate_recommendations(
            was_plan_good, correct_model, cost_can_reduce,
            model_used, response_quality, actual_latency_ms, context, estimated_tokens
        )

        # اقتراح نموذج أفضل
        better_model = None
        if not correct_model and "openai" in model_used.lower():
            better_model = "ollama/llama3 (أسرع وأرخص للمهام البسيطة)"
        elif response_quality < 0.6:
            better_model = "openai/gpt-4o (جودة أعلى للمهام الصعبة)"

        cost_suggestion = None
        if cost_can_reduce:
            cost_suggestion = f"قلّل max_tokens إلى {int(estimated_tokens * 0.8)}"

        report = ReflectionReport(
            report_id=str(uuid.uuid4()),
            task_id=task_id,
            goal_id=goal_id,
            was_plan_good=was_plan_good,
            better_path_exists=not was_plan_good,
            correct_model_used=correct_model,
            cost_can_be_reduced=cost_can_reduce,
            quality_can_increase=quality_can_increase,
            plan_score=round(plan_score, 3),
            efficiency_score=round(efficiency_score, 3),
            quality_score=round(response_quality, 3),
            overall_score=round(overall, 3),
            lessons_learned=lessons,
            recommendations=recommendations,
            actual_latency_ms=actual_latency_ms,
            actual_tokens_used=actual_tokens,
            estimated_tokens=estimated_tokens,
            model_used=model_used,
            better_model_suggestion=better_model,
            cost_saving_suggestion=cost_suggestion,
            metadata=context,
        )

        self._reports.append(report)
        self._lessons_db.extend(lessons)
        self._save_report(report)

        logger.info(
            "self_reflection: task=%s overall=%.2f plan=%.2f efficiency=%.2f quality=%.2f",
            task_id, overall, plan_score, efficiency_score, response_quality
        )

        # Prometheus Metrics
        hajeen_reflection_reports_total.labels(status="success", goal_id=goal_id).inc()
        hajeen_reflection_score_overall.labels(goal_id=goal_id).set(report.overall_score)
        return report

    async def _generate_lessons(
        self, good_plan: bool, correct_model: bool, reduce_cost: bool,
        increase_quality: bool, latency_ms: float, token_ratio: float, model_used: str, quality: float
    ) -> List[str]:
        lessons = []
        if not good_plan:
            lessons.append("الخطة كانت غير مثالية — يجب تقليل عدد الخطوات")
        if not correct_model:
            lessons.append(f"زمن الاستجابة {latency_ms:.0f}ms — اختر نموذجاً أسرع للمهام البسيطة")
        if reduce_cost:
            lessons.append(f"استخدام token_ratio={token_ratio:.1f}x — قلّل max_tokens")
        if increase_quality:
            lessons.append("الجودة تحت 85% — فكّر في نموذج أقوى أو RAG")
        if not lessons:
            lessons.append("أداء ممتاز — حافظ على هذا النهج")
        # Use LLM for more nuanced lessons
        llm_lessons = await self._call_llm_for_reflection(
            "generate_lessons",
            report_data={
                "was_plan_good": good_plan,
                "correct_model_used": correct_model,
                "cost_can_be_reduced": reduce_cost,
                "quality_can_increase": increase_quality,
                "actual_latency_ms": latency_ms,
                "token_efficiency_ratio": token_ratio,
                "model_used": model_used,
                "response_quality": quality
            }
        )
        lessons.extend(llm_lessons)
        return lessons

    async def _generate_recommendations(
        self, good_plan: bool, correct_model: bool,
        reduce_cost: bool, model: str, quality: float, latency_ms: float, context: Dict[str, Any], estimated_tokens: int
    ) -> List[str]:
        recs = []
        if not good_plan:
            recs.append("راجع Graph Planner لتحسين ترتيب الخطوات")
        if not correct_model:
            recs.append("حدّث Model Performance DB بهذه النتائج")
        if reduce_cost:
            recs.append("أضف قاعدة في Policy Engine لتقليل التوكنز")
        if quality < 0.7:
            recs.append("أضف RAG لتعزيز السياق في المهام المشابهة")
        # Use LLM for more nuanced recommendations
        llm_recs = await self._call_llm_for_reflection(
            "generate_recommendations",
            report_data={
                "was_plan_good": good_plan,
                "correct_model_used": correct_model,
                "cost_can_be_reduced": reduce_cost,
                "model_used": model,
                "response_quality": quality
            }
        )
        recs.extend(llm_recs)

        # Apply recommendations to other systems if applicable
        if not correct_model:
            # Example: Update model performance in DB
            # Example: Update model performance in DB
            # Infer provider from model_used (simple heuristic)
            provider = "openai" if "openai" in model.lower() else "ollama"
            # Infer task_type and domain from context, or use generic values
            task_type = context.get("task_type", "general_reflection")
            domain = context.get("domain", "reflection")
            success = quality >= 0.7 # Assuming quality >= 0.7 means success

            self._model_performance_db.record_call(
                model_id=model,
                provider=provider,
                task_type=task_type,
                domain=domain,
                latency_ms=latency_ms,
                tokens_used=estimated_tokens, # Using estimated tokens for recording
                quality_score=quality,
                success=success,
                cost_usd=0.0 # Placeholder, actual cost calculation is complex
            )
        if reduce_cost:
            # Example: Add a policy to reduce tokens for similar tasks
            await self._policy_engine.add_policy(
                name=f"Reduce_Tokens_for_{model}",
                description=f"Reduce max_tokens for {model} when estimated tokens are exceeded.",
                rules={"model": model, "token_efficiency_ratio_gt": 1.3},
                action={"type": "reduce_max_tokens", "factor": 0.8}
            )
        return recs

    def _save_report(self, report: ReflectionReport) -> None:
        try:
            path = self._path / f"{report.report_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("self_reflection: save error: %s", e)

    def get_aggregated_lessons(self, limit: int = 20) -> List[str]:
        """أهم الدروس المجمّعة."""
        from collections import Counter
        counts = Counter(self._lessons_db)
        return [lesson for lesson, _ in counts.most_common(limit)]

    def get_recent_reports(self, limit: int = 10) -> List[Dict]:
        return [r.to_dict() for r in self._reports[-limit:]]

    async def _call_llm_for_reflection(self, reflection_type: str, report_data: Dict[str, Any]) -> List[str]:
        """يستدعي LLM لإجراء استدلال أعمق حول التقييم الذاتي."""
        prompt = f"بصفتك محرك استدلال لـ Hajeen AI، قم بتحليل تقرير التقييم الذاتي التالي واستخرج دروسًا مستفادة أو توصيات بناءً على نوع التقييم المطلوب:\n\nنوع التقييم: {reflection_type}\nبيانات التقرير: {json.dumps(report_data, indent=2)}\n\nاستخرج قائمة من النقاط الموجزة (bullet points) باللغة العربية. ركز على الاستدلال العميق وليس مجرد إعادة صياغة البيانات."

        try:
            # Use DecisionEngine to select the best model for reflection
            from ..goal_manager import ComplexityLevel, Goal, IntentType
            goal = Goal(
                goal_id=str(uuid.uuid4()),
                intent=IntentType.REASONING,
                domain="reflection",
                complexity=ComplexityLevel.MEDIUM,
                original_request="Analyze reflection report",
                final_objective="Generate lessons and recommendations from reflection report",
                sub_tasks=[],
                required_tools=[],
                suitable_models=[],
                confidence=0.9
            )
            with track_latency(hajeen_reflection_latency_seconds):
                decision = await self._decision_engine.decide(
                    task_id=str(uuid.uuid4()),
                    goal=goal,
                    task_name="reflection_analysis",
                    context=report_data
                )
            if not decision.primary_model:
                logger.warning("SelfReflection: No model selected by DecisionEngine for reflection_analysis.")
                return []

            # Assuming DecisionEngine provides a way to get the LLM response
            # This part needs actual implementation based on how DecisionEngine integrates with LLMs
            # For now, we'll simulate a call or use a direct LLM call if DecisionEngine doesn't abstract it fully
            # For demonstration, let's assume a direct call via a mock or simple LLM interface
            # In a real scenario, self._decision_engine.execute_task would be used.
            # For now, let's mock the LLM call or use a simple placeholder.
            # This is a placeholder for actual LLM interaction through DecisionEngine
            # In a real system, DecisionEngine would return the LLM response directly.
            mock_llm_response = {
                "generate_lessons": [
                    "تحليل أعمق: قد تكون المشكلة في تصميم الخطة الأولية وليس فقط عدد الخطوات.",
                    "تحسين اختيار النموذج: يجب أن يأخذ في الاعتبار تعقيد المهمة وليس فقط السرعة الأولية."
                ],
                "generate_recommendations": [
                    "تحديث قاعدة بيانات الأداء: يجب تسجيل الأسباب الجذرية لضعف الأداء.",
                    "تعديل محرك السياسات: إضافة سياسة لفرض استخدام RAG للمهام التي تتطلب جودة عالية."
                ]
            }
            # In a real scenario, this would be an actual LLM call via DecisionEngine
            # Use DecisionEngine to execute the LLM task
            llm_response = await self._decision_engine.execute_llm_task(
                model_id=decision.primary_model,
                prompt=prompt,
                temperature=0.5, # Reflection tasks usually benefit from lower temperature
                max_tokens=500
            )
            # Assuming the LLM response content is a bulleted list in Arabic
            # We need to parse it into a list of strings
            if llm_response and llm_response.content:
                # Simple parsing for bullet points
                return [line.strip() for line in llm_response.content.split('\n') if line.strip().startswith('-') or line.strip().startswith('*')]
            return []

        except Exception as e:
            logger.error("SelfReflection: Error calling LLM for reflection: %s", e)
            hajeen_reflection_reports_total.labels(status="error", goal_id="unknown").inc()
            return []

    def get_average_scores(self) -> Dict[str, float]:
        if not self._reports:
            return {"plan": 0, "efficiency": 0, "quality": 0, "overall": 0}
        n = len(self._reports)
        return {
            "plan": round(sum(r.plan_score for r in self._reports) / n, 3),
            "efficiency": round(sum(r.efficiency_score for r in self._reports) / n, 3),
            "quality": round(sum(r.quality_score for r in self._reports) / n, 3),
            "overall": round(sum(r.overall_score for r in self._reports) / n, 3),
            "total_reflections": n,
        }


# Singleton
_reflector: Optional[SelfReflection] = None


async def get_self_reflection() -> SelfReflection:
    global _reflector
    if _reflector is None:
        _reflector = SelfReflection()
        await _reflector.initialize()
    return _reflector
