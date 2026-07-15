"""
Model Performance Database — قاعدة بيانات أداء النماذج
=========================================================
تسجّل لكل نموذج:
- السرعة، الجودة، التكلفة، معدل النجاح
- أكثر المهام نجاحاً وفشلاً
يستخدمها Decision Engine لاتخاذ قرارات أذكى.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ModelMetrics:
    model_id: str
    provider: str
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0
    total_tokens: int = 0
    total_cost_usd: float = 0
    quality_scores: List[float] = field(default_factory=list)
    task_type_stats: Dict[str, Dict] = field(default_factory=dict)  # task_type → {success, fail}
    domain_stats: Dict[str, Dict] = field(default_factory=dict)
    last_used: float = field(default_factory=time.time)
    first_used: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_latency_ms / self.total_calls

    @property
    def avg_quality(self) -> float:
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores) / len(self.quality_scores)

    @property
    def avg_cost_per_call(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_cost_usd / self.total_calls

    def best_task_types(self, top_k: int = 3) -> List[Tuple[str, float]]:
        results = []
        for task, stats in self.task_type_stats.items():
            total = stats.get("success", 0) + stats.get("fail", 0)
            rate = stats.get("success", 0) / total if total else 0
            results.append((task, rate))
        return sorted(results, key=lambda x: x[1], reverse=True)[:top_k]

    def worst_task_types(self, top_k: int = 3) -> List[Tuple[str, float]]:
        results = self.best_task_types(top_k=100)
        return sorted(results, key=lambda x: x[1])[:top_k]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "total_calls": self.total_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_quality": round(self.avg_quality, 3),
            "avg_cost_per_call": round(self.avg_cost_per_call, 4),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "best_tasks": self.best_task_types(),
            "worst_tasks": self.worst_task_types(),
            "last_used": self.last_used,
        }


class ModelPerformanceDB:
    """
    قاعدة بيانات أداء النماذج.
    تُستخدم بواسطة Decision Engine لاختيار أفضل نموذج.
    """

    def __init__(self, storage_path: str = "storage_data/brain/model_performance") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._metrics: Dict[str, ModelMetrics] = {}
        self._load()

    def _get_or_create(self, model_id: str, provider: str = "unknown") -> ModelMetrics:
        if model_id not in self._metrics:
            self._metrics[model_id] = ModelMetrics(
                model_id=model_id,
                provider=provider,
            )
        return self._metrics[model_id]

    def record_call(
        self,
        model_id: str,
        provider: str,
        task_type: str,
        domain: str,
        latency_ms: float,
        tokens_used: int,
        quality_score: float,
        success: bool,
        cost_usd: float = 0.0,
    ) -> None:
        """تسجيل نتيجة استدعاء نموذج."""
        m = self._get_or_create(model_id, provider)
        m.total_calls += 1
        m.total_latency_ms += latency_ms
        m.total_tokens += tokens_used
        m.total_cost_usd += cost_usd
        m.last_used = time.time()

        if success:
            m.successful_calls += 1
            m.quality_scores.append(quality_score)
            if len(m.quality_scores) > 1000:
                m.quality_scores = m.quality_scores[-500:]
        else:
            m.failed_calls += 1

        # إحصائيات نوع المهمة
        if task_type not in m.task_type_stats:
            m.task_type_stats[task_type] = {"success": 0, "fail": 0}
        m.task_type_stats[task_type]["success" if success else "fail"] += 1

        # إحصائيات المجال
        if domain not in m.domain_stats:
            m.domain_stats[domain] = {"success": 0, "fail": 0}
        m.domain_stats[domain]["success" if success else "fail"] += 1

        logger.debug(
            "perf_db: %s call #%d success=%s latency=%.0fms quality=%.2f",
            model_id, m.total_calls, success, latency_ms, quality_score
        )

        # حفظ دوري
        if m.total_calls % 50 == 0:
            self._save()

    async def get_best_model_for(self, task_type: str, domain: str) -> Optional[Dict[str, Any]]:
        """يُعيد أفضل نموذج لنوع مهمة ومجال معيّنَين."""
        candidates = []
        for model_id, m in self._metrics.items():
            if m.total_calls < 5:
                continue  # بيانات غير كافية
            task_stat = m.task_type_stats.get(task_type, {})
            t = task_stat.get("success", 0) + task_stat.get("fail", 0)
            task_rate = task_stat.get("success", 0) / t if t else m.success_rate
            score = (task_rate * 0.4) + (m.avg_quality * 0.4) + (
                max(0, 1 - m.avg_latency_ms / 10000) * 0.2
            )
            candidates.append({
                "model_id": model_id,
                "score": score,
                "success_rate": m.success_rate,
                "avg_quality": m.avg_quality,
                "avg_latency_ms": m.avg_latency_ms,
            })

        if not candidates:
            return None
        best = max(candidates, key=lambda c: c["score"])
        return best

    def get_model_report(self, model_id: str) -> Optional[Dict[str, Any]]:
        if model_id not in self._metrics:
            return None
        return self._metrics[model_id].to_dict()

    def get_all_models_summary(self) -> List[Dict[str, Any]]:
        return sorted(
            [m.to_dict() for m in self._metrics.values()],
            key=lambda x: x["total_calls"], reverse=True
        )

    def get_leaderboard(self, by: str = "quality") -> List[Dict[str, Any]]:
        """ترتيب النماذج حسب معيار."""
        key_map = {
            "quality": "avg_quality",
            "speed": "avg_latency_ms",
            "success": "success_rate",
        }
        sort_key = key_map.get(by, "avg_quality")
        reverse = sort_key != "avg_latency_ms"
        models = self.get_all_models_summary()
        return sorted(models, key=lambda m: m.get(sort_key, 0), reverse=reverse)

    def get_statistics(self) -> Dict[str, Any]:
        total_calls = sum(m.total_calls for m in self._metrics.values())
        total_cost = sum(m.total_cost_usd for m in self._metrics.values())
        total_tokens = sum(m.total_tokens for m in self._metrics.values())
        return {
            "tracked_models": len(self._metrics),
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 2),
            "best_quality_model": (
                max(self._metrics.keys(), key=lambda k: self._metrics[k].avg_quality)
                if self._metrics else None
            ),
            "fastest_model": (
                min(
                    (k for k in self._metrics if self._metrics[k].avg_latency_ms > 0),
                    key=lambda k: self._metrics[k].avg_latency_ms,
                    default=None,
                )
            ),
        }

    def _save(self) -> None:
        try:
            data = {mid: m.to_dict() for mid, m in self._metrics.items()}
            with open(self._path / "metrics.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("perf_db: save error: %s", e)

    def _load(self) -> None:
        path = self._path / "metrics.json"
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for model_id, md in data.items():
                m = ModelMetrics(
                    model_id=model_id,
                    provider=md.get("provider", "unknown"),
                    total_calls=md.get("total_calls", 0),
                    successful_calls=int(md.get("total_calls", 0) * md.get("success_rate", 0)),
                    failed_calls=int(md.get("total_calls", 0) * (1 - md.get("success_rate", 0))),
                    total_latency_ms=md.get("avg_latency_ms", 0) * md.get("total_calls", 0),
                    total_tokens=md.get("total_tokens", 0),
                    total_cost_usd=md.get("total_cost_usd", 0),
                    quality_scores=[md.get("avg_quality", 0)],
                    last_used=md.get("last_used", now),
                )
                self._metrics[model_id] = m
            logger.info("perf_db: loaded %d model records", len(self._metrics))
        except Exception as e:
            logger.error("perf_db: load error: %s", e)


# Singleton
_perf_db: Optional[ModelPerformanceDB] = None


def get_performance_db() -> ModelPerformanceDB:
    global _perf_db
    if _perf_db is None:
        _perf_db = ModelPerformanceDB()
    return _perf_db
