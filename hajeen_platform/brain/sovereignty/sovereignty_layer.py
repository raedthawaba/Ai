"""
Sovereignty Layer — طبقة السيادة
===================================
أهم طبقة في المشروع.
تتتبع مدى استقلالية Hajeen عن النماذج الخارجية.
الهدف: تقليل الاعتماد على الخارج سنةً بعد سنة.
أي نموذج خارجي = Temporary Expert وليس جزءاً من النظام.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DependencyLevel(str, Enum):
    FULLY_SOVEREIGN = "fully_sovereign"       # 0% اعتماد خارجي
    HIGHLY_SOVEREIGN = "highly_sovereign"     # 0-20%
    SOVEREIGN = "sovereign"                   # 20-40%
    TRANSITIONING = "transitioning"           # 40-60%
    DEPENDENT = "dependent"                   # 60-80%
    HIGHLY_DEPENDENT = "highly_dependent"     # 80-100%


@dataclass
class SovereigntySnapshot:
    """لقطة لمستوى الاستقلالية في لحظة زمنية معينة."""
    snapshot_id: str
    timestamp: float
    total_requests: int
    local_requests: int       # أُجيب بنموذج محلي
    cloud_requests: int       # أُجيب بنموذج سحابي
    rag_requests: int         # أُجيب بـ RAG داخلي
    cached_requests: int      # أُجيب من الكاش
    local_ratio: float
    dependency_level: DependencyLevel
    local_models_used: List[str]
    cloud_models_used: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "total_requests": self.total_requests,
            "local_ratio": round(self.local_ratio, 3),
            "dependency_level": self.dependency_level,
            "local_models_used": self.local_models_used,
            "cloud_models_used": self.cloud_models_used,
        }


class SovereigntyLayer:
    """
    يتتبع ويقيس مدى استقلالية Hajeen عن النماذج الخارجية.

    الهدف النهائي:
    - Year 1: 30% local
    - Year 2: 50% local
    - Year 3: 70% local
    - Year 5: 90% local (Fully Sovereign)
    """

    SOVEREIGNTY_TARGETS = {
        1: 0.30,   # Year 1 target
        2: 0.50,
        3: 0.70,
        5: 0.90,
    }

    def __init__(self, storage_path: str = "storage_data/brain/sovereignty") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._snapshots: List[SovereigntySnapshot] = []
        self._counters = {
            "total": 0,
            "local": 0,
            "cloud": 0,
            "rag": 0,
            "cached": 0,
        }
        self._local_models_used: set = set()
        self._cloud_models_used: set = set()
        self._load_history()
        self._knowledge_transfer_log: List[Dict] = []

    def record_request(
        self,
        model_id: str,
        is_local: bool,
        used_rag: bool = False,
        from_cache: bool = False,
        domain: str = "general",
        quality_score: float = 0.7,
    ) -> None:
        """تسجيل طلب وتصنيفه."""
        self._counters["total"] += 1

        if from_cache:
            self._counters["cached"] += 1
        elif used_rag:
            self._counters["rag"] += 1
        elif is_local:
            self._counters["local"] += 1
            self._local_models_used.add(model_id)
        else:
            self._counters["cloud"] += 1
            self._cloud_models_used.add(model_id)

        # تسجيل نقل المعرفة من الخارجي
        if not is_local:
            self._knowledge_transfer_log.append({
                "model": model_id,
                "domain": domain,
                "quality": quality_score,
                "at": time.time(),
                "note": "External Expert — Knowledge to be internalized",
            })

    def get_sovereignty_ratio(self) -> float:
        """نسبة الاستقلالية الحالية."""
        total = self._counters["total"]
        if total == 0:
            return 0.0
        independent = self._counters["local"] + self._counters["rag"] + self._counters["cached"]
        return independent / total

    def get_dependency_level(self) -> DependencyLevel:
        ratio = self.get_sovereignty_ratio()
        if ratio >= 0.80:
            return DependencyLevel.FULLY_SOVEREIGN
        elif ratio >= 0.60:
            return DependencyLevel.HIGHLY_SOVEREIGN
        elif ratio >= 0.40:
            return DependencyLevel.SOVEREIGN
        elif ratio >= 0.25:
            return DependencyLevel.TRANSITIONING
        elif ratio >= 0.10:
            return DependencyLevel.DEPENDENT
        return DependencyLevel.HIGHLY_DEPENDENT

    def take_snapshot(self) -> SovereigntySnapshot:
        """أخذ لقطة للحالة الحالية وحفظها."""
        import uuid
        snap = SovereigntySnapshot(
            snapshot_id=str(uuid.uuid4()),
            timestamp=time.time(),
            total_requests=self._counters["total"],
            local_requests=self._counters["local"],
            cloud_requests=self._counters["cloud"],
            rag_requests=self._counters["rag"],
            cached_requests=self._counters["cached"],
            local_ratio=self.get_sovereignty_ratio(),
            dependency_level=self.get_dependency_level(),
            local_models_used=list(self._local_models_used),
            cloud_models_used=list(self._cloud_models_used),
        )
        self._snapshots.append(snap)
        self._save_snapshot(snap)
        logger.info(
            "sovereignty: snapshot ratio=%.1f%% level=%s",
            snap.local_ratio * 100, snap.dependency_level
        )
        return snap

    def get_progress_toward_target(self, target_year: int = 1) -> Dict[str, Any]:
        """مدى التقدم نحو هدف سنوي."""
        target = self.SOVEREIGNTY_TARGETS.get(target_year, 0.30)
        current = self.get_sovereignty_ratio()
        progress = min(1.0, current / target) if target > 0 else 0
        return {
            "target_year": target_year,
            "target_ratio": target,
            "current_ratio": round(current, 3),
            "progress": round(progress, 3),
            "progress_percent": round(progress * 100, 1),
            "remaining": round(target - current, 3),
            "on_track": current >= target * 0.8,
        }

    def get_knowledge_transfer_summary(self) -> Dict[str, Any]:
        """ملخص المعرفة المكتسبة من النماذج الخارجية."""
        if not self._knowledge_transfer_log:
            return {"total_transfers": 0}
        by_model: Dict[str, int] = {}
        by_domain: Dict[str, int] = {}
        for entry in self._knowledge_transfer_log:
            m = entry["model"]
            d = entry["domain"]
            by_model[m] = by_model.get(m, 0) + 1
            by_domain[d] = by_domain.get(d, 0) + 1
        return {
            "total_transfers": len(self._knowledge_transfer_log),
            "by_model": by_model,
            "by_domain": by_domain,
            "note": "كل نقل معرفي = فرصة للتعلم الداخلي",
        }

    def get_sovereignty_report(self) -> Dict[str, Any]:
        """تقرير شامل عن الاستقلالية."""
        current_ratio = self.get_sovereignty_ratio()
        level = self.get_dependency_level()
        return {
            "current_sovereignty_ratio": round(current_ratio, 3),
            "current_level": level,
            "counters": dict(self._counters),
            "local_models": list(self._local_models_used),
            "external_models": list(self._cloud_models_used),
            "external_count": len(self._cloud_models_used),
            "external_note": "هذه النماذج مؤقتة — Temporary Experts",
            "yearly_targets": self.SOVEREIGNTY_TARGETS,
            "year_1_progress": self.get_progress_toward_target(1),
            "year_3_progress": self.get_progress_toward_target(3),
            "knowledge_transfers": self.get_knowledge_transfer_summary(),
            "snapshots_taken": len(self._snapshots),
            "mission": (
                "أي معرفة تأتي من نموذج خارجي يجب أن تتحول تدريجياً "
                "إلى معرفة داخلية يمتلكها Hajeen."
            ),
        }

    def _save_snapshot(self, snap: SovereigntySnapshot) -> None:
        try:
            path = self._path / f"snapshot_{int(snap.timestamp)}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snap.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("sovereignty: save error: %s", e)

    def _load_history(self) -> None:
        try:
            summary_path = self._path / "counters.json"
            if summary_path.exists():
                with open(summary_path, encoding="utf-8") as f:
                    self._counters = json.load(f)
        except Exception:
            pass

    def save_counters(self) -> None:
        try:
            with open(self._path / "counters.json", "w", encoding="utf-8") as f:
                json.dump(self._counters, f)
        except Exception as e:
            logger.error("sovereignty: save counters error: %s", e)


# Singleton
_sovereignty: Optional[SovereigntyLayer] = None


def get_sovereignty_layer() -> SovereigntyLayer:
    global _sovereignty
    if _sovereignty is None:
        _sovereignty = SovereigntyLayer()
    return _sovereignty
