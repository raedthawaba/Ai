"""Phase 8.3 — Request Handler: معالجة وتحقق طلبات الـ inference."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.llm.base import LLMMessage, LLMRequest


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class InferenceJob:
    """وحدة عمل inference واحدة."""
    request: LLMRequest
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    priority: int = 5
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    cancelled: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def wait_time_ms(self) -> float:
        if self.started_at:
            return (self.started_at - self.created_at) * 1000
        return (time.time() - self.created_at) * 1000

    @property
    def execution_time_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0

    def cancel(self) -> None:
        self.cancelled = True
        self.status = JobStatus.CANCELLED

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "priority": self.priority,
            "wait_ms": round(self.wait_time_ms, 2),
            "exec_ms": round(self.execution_time_ms, 2),
            "error": self.error,
        }


class RequestHandler:
    """
    معالجة وتحقق طلبات الـ inference.

    المهام:
    - تحويل المدخلات إلى InferenceJob
    - التحقق من صحة الطلبات
    - إضافة request IDs
    - تحديد الأولوية
    """

    def __init__(
        self,
        default_max_tokens: int = 1024,
        default_temperature: float = 0.7,
        max_message_length: int = 50000,
    ):
        self.default_max_tokens = default_max_tokens
        self.default_temperature = default_temperature
        self.max_message_length = max_message_length

    def create_job(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        session_id: Optional[str] = None,
        priority: int = 5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InferenceJob:
        """إنشاء InferenceJob من المعطيات."""
        request_id = str(uuid.uuid4())

        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in messages
            if m.get("content")
        ]

        request = LLMRequest(
            messages=llm_messages,
            model=model,
            temperature=temperature or self.default_temperature,
            max_tokens=max_tokens or self.default_max_tokens,
            stream=stream,
            session_id=session_id,
            request_id=request_id,
            metadata=metadata or {},
        )

        return InferenceJob(
            request=request,
            priority=priority,
            metadata=metadata or {},
        )

    def from_llm_request(
        self,
        request: LLMRequest,
        priority: int = 5,
    ) -> InferenceJob:
        """إنشاء job من LLMRequest موجود."""
        if not request.request_id:
            request.request_id = str(uuid.uuid4())
        return InferenceJob(request=request, priority=priority)

    def validate(self, job: InferenceJob) -> List[str]:
        """التحقق من صحة الـ job. يرجع قائمة الأخطاء."""
        errors = []

        if not job.request.messages:
            errors.append("No messages provided")

        for msg in job.request.messages:
            if msg.role not in ("system", "user", "assistant"):
                errors.append(f"Invalid role: {msg.role}")
            if len(msg.content) > self.max_message_length:
                errors.append(f"Message too long: {len(msg.content)} chars")

        has_user = any(m.role == "user" for m in job.request.messages)
        if not has_user:
            errors.append("At least one user message is required")

        max_tokens = job.request.max_tokens or self.default_max_tokens
        if max_tokens > 32000:
            errors.append(f"max_tokens too large: {max_tokens} > 32000")

        return errors
