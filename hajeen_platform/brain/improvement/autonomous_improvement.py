"""
Autonomous Improvement — التحسين الذاتي الأسبوعي
===================================================
كل أسبوع يقوم النظام بتحليل:
- أكثر الأخطاء
- أكثر الطلبات
- أكثر الأدوات استخداماً
- أكثر النماذج استخداماً
ثم يقترح: تحسينات، وحدات جديدة، تدريب جديد، إعادة تنظيم.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ImprovementType(str, Enum):
    PERFORMANCE = "performance"
    TRAINING = "training"
    ARCHITECTURE = "architecture"
    TOOLING = "tooling"
    REORGANIZATION = "reorganization"
    NEW_MODULE = "new_module"
    COST_REDUCTION = "cost_reduction"
    QUALITY_IMPROVEMENT = "quality_improvement"


class ImprovementPriority(int, Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class ImprovementSuggestion:
    suggestion_id: str
    improvement_type: ImprovementType
    priority: ImprovementPriority
    title: str
    description: str
    evidence: List[str]       # الأدلة من التحليل
    expected_impact: str
    implementation_steps: List[str]
    estimated_effort: str     # hours | days | weeks
    auto_applicable: bool     # هل يمكن تطبيقه تلقائياً؟
    created_at: float = field(default_factory=time.time)
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "type": self.improvement_type,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "expected_impact": self.expected_impact,
            "steps": self.implementation_steps,
            "estimated_effort": self.estimated_effort,
            "auto_applicable": self.auto_applicable,
            "applied": self.applied,
        }


@dataclass
class WeeklyAnalysisReport:
    report_id: str
    week_start: float
    week_end: float
    # الإحصائيات
    total_requests: int
    top_errors: List[Dict]
    top_request_types: List[Dict]
    top_tools: List[Dict]
    top_models: List[Dict]
    # النتائج
    suggestions: List[ImprovementSuggestion]
    sovereignty_progress: float
    quality_trend: str       # improving | stable | declining
    cost_trend: str
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "total_requests": self.total_requests,
            "top_errors": self.top_errors,
            "top_request_types": self.top_request_types,
            "top_models": self.top_models,
            "suggestions_count": len(self.suggestions),
            "suggestions": [s.to_dict() for s in self.suggestions],
            "quality_trend": self.quality_trend,
            "cost_trend": self.cost_trend,
            "sovereignty_progress": self.sovereignty_progress,
        }


class AutonomousImprovement:
    """
    محرك التحسين الذاتي.
    يحلّل بيانات الأسبوع ويقترح تحسينات ملموسة.
    """

    def __init__(self, storage_path: str = "storage_data/brain/improvement") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._reports: List[WeeklyAnalysisReport] = []
        self._all_suggestions: List[ImprovementSuggestion] = []
        self._error_log: List[Dict] = []
        self._request_log: List[Dict] = []

    def record_error(self, error_type: str, description: str, context: Optional[Dict] = None) -> None:
        self._error_log.append({
            "error_type": error_type,
            "description": description,
            "context": context or {},
            "at": time.time(),
        })

    def record_request(self, request_type: str, domain: str, tool_used: Optional[str], model_used: str) -> None:
        self._request_log.append({
            "request_type": request_type,
            "domain": domain,
            "tool_used": tool_used,
            "model_used": model_used,
            "at": time.time(),
        })

    async def run_weekly_analysis(
        self,
        performance_data: Optional[Dict] = None,
        reflection_data: Optional[List[Dict]] = None,
        sovereignty_data: Optional[Dict] = None,
        distillation_data: Optional[Dict] = None,
    ) -> WeeklyAnalysisReport:
        """تنفيذ التحليل الأسبوعي."""
        now = time.time()
        week_start = now - (7 * 24 * 3600)

        performance_data = performance_data or {}
        reflection_data = reflection_data or []
        sovereignty_data = sovereignty_data or {}
        distillation_data = distillation_data or {}

        # تحليل الأخطاء
        recent_errors = [e for e in self._error_log if e["at"] >= week_start]
        top_errors = self._count_by_field(recent_errors, "error_type", top_k=5)

        # تحليل الطلبات
        recent_requests = [r for r in self._request_log if r["at"] >= week_start]
        top_request_types = self._count_by_field(recent_requests, "request_type", top_k=5)
        top_tools = self._count_by_field(recent_requests, "tool_used", top_k=5)
        top_models = self._count_by_field(recent_requests, "model_used", top_k=5)

        # توليد الاقتراحات
        suggestions = self._generate_suggestions(
            top_errors, top_request_types, top_tools, top_models,
            performance_data, reflection_data, sovereignty_data, distillation_data
        )

        # تحليل الاتجاهات
        quality_trend = self._analyze_quality_trend(reflection_data)
        cost_trend = self._analyze_cost_trend(performance_data)
        sovereignty_progress = sovereignty_data.get("year_1_progress", {}).get("progress", 0)

        report = WeeklyAnalysisReport(
            report_id=str(uuid.uuid4()),
            week_start=week_start,
            week_end=now,
            total_requests=len(recent_requests),
            top_errors=top_errors,
            top_request_types=top_request_types,
            top_tools=top_tools,
            top_models=top_models,
            suggestions=suggestions,
            sovereignty_progress=sovereignty_progress,
            quality_trend=quality_trend,
            cost_trend=cost_trend,
        )

        self._reports.append(report)
        self._all_suggestions.extend(suggestions)
        self._save_report(report)

        logger.info(
            "autonomous_improvement: weekly analysis done: %d requests, %d suggestions",
            len(recent_requests), len(suggestions)
        )
        return report

    def _count_by_field(self, items: List[Dict], field: str, top_k: int = 5) -> List[Dict]:
        counts: Dict[str, int] = {}
        for item in items:
            val = str(item.get(field, "unknown"))
            counts[val] = counts.get(val, 0) + 1
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"name": k, "count": v} for k, v in sorted_items[:top_k]]

    def _generate_suggestions(
        self, errors, request_types, tools, models,
        perf_data, reflections, sovereignty, distillation
    ) -> List[ImprovementSuggestion]:
        suggestions: List[ImprovementSuggestion] = []

        # اقتراح 1: إذا كانت هناك أخطاء كثيرة من نوع معين
        if errors:
            top_error = errors[0]
            if top_error["count"] > 5:
                suggestions.append(ImprovementSuggestion(
                    suggestion_id=str(uuid.uuid4()),
                    improvement_type=ImprovementType.PERFORMANCE,
                    priority=ImprovementPriority.HIGH,
                    title=f"معالجة الخطأ المتكرر: {top_error['name']}",
                    description=f"هذا الخطأ تكرر {top_error['count']} مرة هذا الأسبوع",
                    evidence=[f"تكرر {top_error['count']} مرة"],
                    expected_impact="تخفيض معدل الفشل بـ 30-50%",
                    implementation_steps=[
                        f"فحص سجلات الخطأ: {top_error['name']}",
                        "إضافة معالجة خاصة في State Machine",
                        "إضافة اختبارات وحدة",
                    ],
                    estimated_effort="days",
                    auto_applicable=False,
                ))

        # اقتراح 2: إذا كانت نسبة الاستقلالية منخفضة
        sovereignty_ratio = sovereignty.get("current_sovereignty_ratio", 0)
        if sovereignty_ratio < 0.3:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                improvement_type=ImprovementType.TRAINING,
                priority=ImprovementPriority.HIGH,
                title="تدريب نموذج محلي لمجالات الاعتماد العالي",
                description=f"نسبة الاستقلالية {sovereignty_ratio:.1%} — أقل من الهدف 30%",
                evidence=[f"نسبة الاستقلالية: {sovereignty_ratio:.1%}"],
                expected_impact="رفع الاستقلالية 10-15% خلال شهر",
                implementation_steps=[
                    "جمع بيانات التدريب من Knowledge Distillation Pipeline",
                    "تشغيل Continuous Learning Pipeline",
                    "تقييم النموذج الجديد",
                    "نشر النموذج المحلي الجديد",
                ],
                estimated_effort="weeks",
                auto_applicable=False,
            ))

        # اقتراح 3: إذا كان أداء نموذج معين سيئاً
        if models and perf_data.get("total_calls", 0) > 20:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                improvement_type=ImprovementType.QUALITY_IMPROVEMENT,
                priority=ImprovementPriority.MEDIUM,
                title="تحديث أوزان Router بناءً على بيانات الأداء",
                description="تحديث قواعد اختيار النماذج بناءً على أداء الأسبوع الماضي",
                evidence=["بيانات Model Performance DB"],
                expected_impact="تحسين جودة الإجابات 5-10%",
                implementation_steps=[
                    "قراءة تقرير Model Performance DB",
                    "تحديث ROUTING_WEIGHTS في Model Router",
                    "تشغيل Self Evolution لتطبيق التغييرات",
                ],
                estimated_effort="hours",
                auto_applicable=True,
            ))

        # اقتراح 4: إذا كانت بيانات Distillation كثيرة بما يكفي للتدريب
        approved_samples = distillation.get("pending_training", 0)
        if approved_samples >= 50:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                improvement_type=ImprovementType.TRAINING,
                priority=ImprovementPriority.MEDIUM,
                title=f"تشغيل Continuous Learning Pipeline ({approved_samples} عيّنة)",
                description=f"تراكمت {approved_samples} عيّنة معتمدة — الوقت المناسب للتدريب",
                evidence=[f"{approved_samples} عيّنة معتمدة في Distillation DB"],
                expected_impact="تحسين قدرات النموذج المحلي",
                implementation_steps=[
                    "استدعاء ContinuousLearningPipeline.run()",
                    "مراجعة نتائج التقييم",
                    "نشر النموذج إذا اجتاز المعايير",
                ],
                estimated_effort="days",
                auto_applicable=False,
            ))

        # اقتراح 5: أدوات جديدة بناءً على الطلبات
        if request_types:
            most_common = request_types[0]["name"]
            suggestions.append(ImprovementSuggestion(
                suggestion_id=str(uuid.uuid4()),
                improvement_type=ImprovementType.TOOLING,
                priority=ImprovementPriority.LOW,
                title=f"تحسين دعم النوع الأكثر طلباً: {most_common}",
                description=f"النوع '{most_common}' هو الأكثر شيوعاً هذا الأسبوع",
                evidence=[f"{request_types[0]['count']} طلب من نوع {most_common}"],
                expected_impact="تسريع المعالجة 10-20% للطلبات الشائعة",
                implementation_steps=[
                    f"إضافة قالب محسّن لـ {most_common} في Goal Manager",
                    "إضافة Procedure في Procedural Memory",
                    "اختبار التحسينات",
                ],
                estimated_effort="hours",
                auto_applicable=False,
            ))

        return suggestions

    def _analyze_quality_trend(self, reflections: List[Dict]) -> str:
        if len(reflections) < 2:
            return "stable"
        scores = [r.get("overall_score", 0) for r in reflections[-10:]]
        if not scores:
            return "stable"
        mid = len(scores) // 2
        first_half = sum(scores[:mid]) / mid if mid else 0
        second_half = sum(scores[mid:]) / max(len(scores) - mid, 1)
        if second_half > first_half * 1.05:
            return "improving"
        elif second_half < first_half * 0.95:
            return "declining"
        return "stable"

    def _analyze_cost_trend(self, perf_data: Dict) -> str:
        # تحليل مبسط — يمكن توسيعه بمزيد من البيانات
        cloud_calls = perf_data.get("cloud_model_calls", 0)
        total_calls = perf_data.get("total_calls", 1)
        cloud_ratio = cloud_calls / total_calls
        if cloud_ratio > 0.6:
            return "high_cost"
        elif cloud_ratio < 0.3:
            return "optimal"
        return "moderate"

    def _save_report(self, report: WeeklyAnalysisReport) -> None:
        try:
            path = self._path / f"weekly_{report.report_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("autonomous_improvement: save error: %s", e)

    def get_latest_report(self) -> Optional[WeeklyAnalysisReport]:
        return self._reports[-1] if self._reports else None

    def get_pending_suggestions(self) -> List[ImprovementSuggestion]:
        return [s for s in self._all_suggestions if not s.applied]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_reports": len(self._reports),
            "total_suggestions": len(self._all_suggestions),
            "applied": sum(1 for s in self._all_suggestions if s.applied),
            "pending": len(self.get_pending_suggestions()),
            "errors_logged": len(self._error_log),
            "requests_logged": len(self._request_log),
        }


# Singleton
_improvement: Optional[AutonomousImprovement] = None


def get_autonomous_improvement() -> AutonomousImprovement:
    global _improvement
    if _improvement is None:
        _improvement = AutonomousImprovement()
    return _improvement
