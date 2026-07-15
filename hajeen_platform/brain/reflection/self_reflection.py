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
        lessons = self._generate_lessons(
            was_plan_good, correct_model, cost_can_reduce, quality_can_increase,
            actual_latency_ms, token_ratio
        )
        recommendations = self._generate_recommendations(
            was_plan_good, correct_model, cost_can_reduce,
            model_used, response_quality
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
        return report

    def _generate_lessons(
        self, good_plan: bool, correct_model: bool, reduce_cost: bool,
        increase_quality: bool, latency_ms: float, token_ratio: float
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
        return lessons

    def _generate_recommendations(
        self, good_plan: bool, correct_model: bool,
        reduce_cost: bool, model: str, quality: float
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
_reflection: Optional[SelfReflection] = None


def get_self_reflection() -> SelfReflection:
    global _reflection
    if _reflection is None:
        _reflection = SelfReflection()
    return _reflection
