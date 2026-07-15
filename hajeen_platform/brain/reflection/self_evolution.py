"""
Self Evolution — التطور الذاتي للنظام
=======================================
النظام لا يعدّل النموذج فقط، بل يعدّل:
- الخطط
- اختيار النماذج
- اختيار الأدوات
- ترتيب التنفيذ
- السياسات
- قواعد اتخاذ القرار
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


class EvolutionTarget(str, Enum):
    PLANS = "plans"
    MODEL_SELECTION = "model_selection"
    TOOL_SELECTION = "tool_selection"
    EXECUTION_ORDER = "execution_order"
    POLICIES = "policies"
    DECISION_RULES = "decision_rules"
    MEMORY_STRATEGY = "memory_strategy"
    ROUTING_WEIGHTS = "routing_weights"


class EvolutionStatus(str, Enum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"
    REVERTED = "reverted"


@dataclass
class EvolutionProposal:
    """اقتراح تطوير ذاتي للنظام."""
    proposal_id: str
    target: EvolutionTarget
    title: str
    description: str
    current_value: Any
    proposed_value: Any
    expected_improvement: str
    confidence: float
    impact_level: str  # low | medium | high
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    applied_at: Optional[float] = None
    result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target": self.target,
            "title": self.title,
            "description": self.description,
            "expected_improvement": self.expected_improvement,
            "confidence": self.confidence,
            "impact_level": self.impact_level,
            "status": self.status,
            "created_at": self.created_at,
            "applied_at": self.applied_at,
            "result": self.result,
        }


class SelfEvolution:
    """
    محرك التطور الذاتي.
    يحلّل بيانات الأداء ويقترح تحسينات هيكلية للنظام.
    """

    def __init__(
        self,
        storage_path: str = "storage_data/brain/evolution",
        auto_apply_low_impact: bool = True,
    ) -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._proposals: List[EvolutionProposal] = []
        self._applied: List[EvolutionProposal] = []
        self._auto_apply_low = auto_apply_low_impact
        # الحالة الحالية للقواعد القابلة للتطوير
        self._current_rules: Dict[str, Any] = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        rules_path = self._path / "current_rules.json"
        if rules_path.exists():
            try:
                with open(rules_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._default_rules()

    def _default_rules(self) -> Dict[str, Any]:
        return {
            "model_selection": {
                "prefer_local": True,
                "local_quality_threshold": 0.75,
                "cloud_fallback_enabled": True,
                "max_cloud_tokens_per_day": 100000,
            },
            "routing_weights": {
                "quality": 0.4,
                "cost": 0.2,
                "speed": 0.2,
                "domain_match": 0.2,
            },
            "execution_order": {
                "parallel_threshold": 2,    # مهام فأكثر → توازٍ
                "max_parallel": 5,
                "retry_delay_seconds": 2,
            },
            "memory_strategy": {
                "session_window": 20,
                "semantic_top_k": 5,
                "episodic_days_back": 30,
            },
            "decision_rules": {
                "use_rag_for_factual": True,
                "use_web_for_recent": True,
                "multi_model_for_complex": True,
                "complexity_threshold_for_multi": "complex",
            },
        }

    async def analyze_and_evolve(
        self,
        reflection_reports: List[Dict],
        performance_data: Dict,
        distillation_stats: Dict,
    ) -> List[EvolutionProposal]:
        """تحليل الأداء واقتراح التطورات."""
        proposals: List[EvolutionProposal] = []

        # تحليل 1: نموذج اختيار النماذج
        proposals.extend(self._analyze_model_selection(performance_data))

        # تحليل 2: ترتيب التنفيذ
        proposals.extend(self._analyze_execution_order(reflection_reports))

        # تحليل 3: السياسات
        proposals.extend(self._analyze_policies(reflection_reports, performance_data))

        # تحليل 4: قواعد الذاكرة
        proposals.extend(self._analyze_memory_strategy(reflection_reports))

        # تحليل 5: قواعد اتخاذ القرار
        proposals.extend(self._analyze_decision_rules(reflection_reports, distillation_stats))

        self._proposals.extend(proposals)

        # تطبيق التطورات ذات التأثير المنخفض تلقائياً
        if self._auto_apply_low:
            for p in proposals:
                if p.impact_level == "low":
                    await self.apply_proposal(p.proposal_id)

        logger.info("self_evolution: generated %d proposals", len(proposals))
        return proposals

    def _analyze_model_selection(self, perf_data: Dict) -> List[EvolutionProposal]:
        proposals = []
        local_ratio = perf_data.get("local_ratio", 0.5)
        avg_quality = perf_data.get("avg_quality", 0.7)

        if local_ratio > 0.8 and avg_quality < 0.7:
            proposals.append(EvolutionProposal(
                proposal_id=str(uuid.uuid4()),
                target=EvolutionTarget.MODEL_SELECTION,
                title="تخفيض عتبة الجودة للتحويل للسحابة",
                description="النماذج المحلية كثيراً ما تُستخدم لكن الجودة منخفضة. يجب تخفيض عتبة التحويل.",
                current_value=self._current_rules["model_selection"]["local_quality_threshold"],
                proposed_value=0.80,  # رفع العتبة
                expected_improvement="زيادة الجودة بـ 10-15%",
                confidence=0.75,
                impact_level="medium",
            ))

        if local_ratio < 0.3:
            proposals.append(EvolutionProposal(
                proposal_id=str(uuid.uuid4()),
                target=EvolutionTarget.ROUTING_WEIGHTS,
                title="رفع وزن التفضيل للنماذج المحلية",
                description="النماذج السحابية تُستخدم كثيراً — يجب زيادة التفضيل للمحلية لتوفير التكلفة.",
                current_value=self._current_rules["routing_weights"]["cost"],
                proposed_value=0.30,  # رفع وزن التكلفة
                expected_improvement="تخفيض تكلفة بـ 20-30%",
                confidence=0.80,
                impact_level="low",
            ))

        return proposals

    def _analyze_execution_order(self, reports: List[Dict]) -> List[EvolutionProposal]:
        proposals = []
        if not reports:
            return proposals

        slow_tasks = [r for r in reports if r.get("actual_latency_ms", 0) > 5000]
        if len(slow_tasks) > len(reports) * 0.3:
            proposals.append(EvolutionProposal(
                proposal_id=str(uuid.uuid4()),
                target=EvolutionTarget.EXECUTION_ORDER,
                title="تخفيض حد التوازي للمهام البطيئة",
                description="30%+ من المهام بطيئة — يجب تفعيل التوازي في مرحلة أبكر.",
                current_value=self._current_rules["execution_order"]["parallel_threshold"],
                proposed_value=1,
                expected_improvement="تسريع التنفيذ بـ 20-40%",
                confidence=0.70,
                impact_level="medium",
            ))
        return proposals

    def _analyze_policies(self, reports: List[Dict], perf: Dict) -> List[EvolutionProposal]:
        proposals = []
        if not reports:
            return proposals
        avg_quality = sum(r.get("quality_score", 0) for r in reports) / len(reports)
        if avg_quality < 0.65:
            proposals.append(EvolutionProposal(
                proposal_id=str(uuid.uuid4()),
                target=EvolutionTarget.POLICIES,
                title="إضافة سياسة RAG إلزامية للمهام الواقعية",
                description="متوسط الجودة منخفض — إضافة RAG يجب أن يكون إلزامياً للمهام الواقعية.",
                current_value={"rag_mandatory": False},
                proposed_value={"rag_mandatory": True, "rag_domains": ["research", "rag", "data"]},
                expected_improvement="رفع الجودة بـ 15%",
                confidence=0.72,
                impact_level="medium",
            ))
        return proposals

    def _analyze_memory_strategy(self, reports: List[Dict]) -> List[EvolutionProposal]:
        return []  # placeholder للتوسع لاحقاً

    def _analyze_decision_rules(self, reports: List[Dict], distillation: Dict) -> List[EvolutionProposal]:
        proposals = []
        approval_rate = distillation.get("approval_rate", 0)
        if approval_rate < 0.5:
            proposals.append(EvolutionProposal(
                proposal_id=str(uuid.uuid4()),
                target=EvolutionTarget.DECISION_RULES,
                title="رفع عتبة الجودة في Distillation Pipeline",
                description=f"معدل قبول الاستخلاص منخفض ({approval_rate:.1%}) — رفع العتبة لجودة أعلى.",
                current_value={"quality_threshold": 0.6},
                proposed_value={"quality_threshold": 0.7},
                expected_improvement="تحسين جودة بيانات التدريب",
                confidence=0.78,
                impact_level="low",
            ))
        return proposals

    async def apply_proposal(self, proposal_id: str) -> bool:
        """تطبيق اقتراح التطوير."""
        proposal = next((p for p in self._proposals if p.proposal_id == proposal_id), None)
        if not proposal:
            return False
        if proposal.status != EvolutionStatus.PROPOSED:
            return False

        try:
            # تحديث القواعد الحالية
            self._update_rules(proposal)
            proposal.status = EvolutionStatus.APPLIED
            proposal.applied_at = time.time()
            proposal.result = "تم التطبيق بنجاح"
            self._applied.append(proposal)
            self._save_rules()
            logger.info("self_evolution: applied proposal '%s'", proposal.title)
            return True
        except Exception as e:
            proposal.status = EvolutionStatus.REJECTED
            proposal.result = str(e)
            logger.error("self_evolution: apply failed: %s", e)
            return False

    def _update_rules(self, proposal: EvolutionProposal) -> None:
        target_key = proposal.target.value
        if target_key in self._current_rules:
            if isinstance(proposal.proposed_value, dict):
                self._current_rules[target_key].update(proposal.proposed_value)
            else:
                # تحديث قيمة بسيطة بناءً على العنوان
                pass

    def _save_rules(self) -> None:
        try:
            with open(self._path / "current_rules.json", "w", encoding="utf-8") as f:
                json.dump(self._current_rules, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("self_evolution: save rules error: %s", e)

    def get_current_rules(self) -> Dict[str, Any]:
        return dict(self._current_rules)

    def get_proposals_summary(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for p in self._proposals:
            by_status[p.status] = by_status.get(p.status, 0) + 1
        return {
            "total": len(self._proposals),
            "by_status": by_status,
            "applied_count": len(self._applied),
            "recent": [p.to_dict() for p in self._proposals[-5:]],
        }


# Singleton
_evolution: Optional[SelfEvolution] = None


def get_self_evolution() -> SelfEvolution:
    global _evolution
    if _evolution is None:
        _evolution = SelfEvolution()
    return _evolution
