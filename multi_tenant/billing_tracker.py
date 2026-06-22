"""Billing Tracker — tracks per-tenant token usage, GPU time, and compute costs."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PRICING: Dict[str, float] = {
    "tokens_input_per_1k": 0.002,
    "tokens_output_per_1k": 0.004,
    "gpu_minute": 0.08,
    "storage_gb_month": 0.023,
    "api_call": 0.0001,
}


@dataclass
class UsageRecord:
    tenant_id: str
    timestamp: float
    operation: str
    input_tokens: int = 0
    output_tokens: int = 0
    gpu_seconds: float = 0.0
    cost_usd: float = 0.0
    model: str = ""
    request_id: str = ""


class BillingTracker:
    """Records usage events and computes billing totals."""

    def __init__(self, db: Any, redis_client: Any) -> None:
        self.db = db
        self.redis = redis_client

    def record_inference(
        self,
        tenant_id: str,
        input_tokens: int,
        output_tokens: int,
        gpu_seconds: float,
        model: str,
        request_id: str,
    ) -> UsageRecord:
        cost = (
            (input_tokens / 1000) * PRICING["tokens_input_per_1k"]
            + (output_tokens / 1000) * PRICING["tokens_output_per_1k"]
            + (gpu_seconds / 60) * PRICING["gpu_minute"]
            + PRICING["api_call"]
        )
        record = UsageRecord(
            tenant_id=tenant_id,
            timestamp=time.time(),
            operation="inference",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            gpu_seconds=gpu_seconds,
            cost_usd=round(cost, 6),
            model=model,
            request_id=request_id,
        )
        self._persist(record)
        self._update_redis_counters(record)
        return record

    def get_monthly_usage(self, tenant_id: str, year: int, month: int) -> Dict[str, Any]:
        rows = self.db.fetchall(
            """SELECT
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(gpu_seconds) as total_gpu_seconds,
               SUM(cost_usd) as total_cost,
               COUNT(*) as total_requests
               FROM usage_records
               WHERE tenant_id = %s
               AND EXTRACT(YEAR FROM TO_TIMESTAMP(timestamp)) = %s
               AND EXTRACT(MONTH FROM TO_TIMESTAMP(timestamp)) = %s""",
            (tenant_id, year, month),
        )
        row = rows[0] if rows else {}
        return {
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
            "total_input_tokens": row.get("total_input", 0) or 0,
            "total_output_tokens": row.get("total_output", 0) or 0,
            "total_gpu_minutes": round((row.get("total_gpu_seconds", 0) or 0) / 60, 2),
            "total_cost_usd": round(row.get("total_cost", 0) or 0, 4),
            "total_requests": row.get("total_requests", 0) or 0,
        }

    def _persist(self, record: UsageRecord) -> None:
        self.db.execute(
            """INSERT INTO usage_records
               (tenant_id, timestamp, operation, input_tokens, output_tokens,
                gpu_seconds, cost_usd, model, request_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (record.tenant_id, record.timestamp, record.operation,
             record.input_tokens, record.output_tokens, record.gpu_seconds,
             record.cost_usd, record.model, record.request_id),
        )

    def _update_redis_counters(self, record: UsageRecord) -> None:
        from datetime import datetime, timezone
        month = datetime.now(timezone.utc).strftime("%Y%m")
        pipe = self.redis.pipeline()
        pipe.incrbyfloat(f"billing:{record.tenant_id}:{month}:cost", record.cost_usd)
        pipe.incrby(f"billing:{record.tenant_id}:{month}:requests", 1)
        pipe.execute()
