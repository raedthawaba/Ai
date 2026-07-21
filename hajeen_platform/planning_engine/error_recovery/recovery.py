"""Planning Engine - Error Recovery System."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ErrorSeverity(str, Enum):
    """شدة الخطأ."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(str, Enum):
    """إجراءات الاسترداد."""
    RETRY = "retry"
    FALLBACK = "fallback"
    SKIP = "skip"
    ABORT = "abort"
    ESCALATE = "escalate"


@dataclass
class RecoveryPolicy:
    """سياسة الاسترداد."""
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    exponential_backoff: bool = True
    max_delay_seconds: float = 60.0
    jitter: bool = True
    fallback_enabled: bool = True
    skip_on_retry_exhausted: bool = False


@dataclass
class ErrorContext:
    """سياق الخطأ."""
    error_id: str
    error_type: str
    error_message: str
    timestamp: float
    severity: ErrorSeverity
    
    # المصدر
    source: str = ""
    plan_id: Optional[str] = None
    step_id: Optional[str] = None
    
    # التتبع
    stack_trace: Optional[str] = None
    previous_errors: List[Dict[str, Any]] = field(default_factory=list)
    
    # البيانات
    context_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecoveryResult:
    """نتيجة الاسترداد."""
    success: bool
    action_taken: RecoveryAction
    recovered: bool
    attempts: int
    total_duration_ms: float
    error_message: Optional[str] = None
    fallback_result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class RetryStrategy:
    """استراتيجية إعادة المحاولة."""

    @staticmethod
    def exponential_backoff(
        attempt: int,
        base_delay: float,
        max_delay: float,
        jitter: bool = True,
    ) -> float:
        """حساب التأخير باستخدام exponential backoff."""
        delay = base_delay * (2 ** attempt)
        delay = min(delay, max_delay)
        
        if jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay

    @staticmethod
    def linear_backoff(
        attempt: int,
        base_delay: float,
        max_delay: float,
    ) -> float:
        """حساب التأخير باستخدام linear backoff."""
        return min(base_delay * (attempt + 1), max_delay)

    @staticmethod
    def constant_backoff(
        attempt: int,
        delay: float,
    ) -> float:
        """تأخير ثابت."""
        return delay


class ErrorRecoveryManager:
    """
    مدير استرداد الأخطاء.
    
    الميزات:
    - إعادة المحاولة مع backoff
    - Fallback mechanisms
    - Error categorization
    - Recovery policies
    - Error tracking and reporting
    """

    def __init__(self, default_policy: Optional[RecoveryPolicy] = None) -> None:
        self._default_policy = default_policy or RecoveryPolicy()
        self._policies: Dict[str, RecoveryPolicy] = {}
        self._error_history: List[ErrorContext] = []
        self._max_history = 1000
        self._fallback_handlers: Dict[str, Callable[[ErrorContext], Any]] = {}
        self._lock = asyncio.Lock()

    def set_policy(self, error_type: str, policy: RecoveryPolicy) -> None:
        """تعيين سياسة لاسترداد خطأ معين."""
        self._policies[error_type] = policy
        logger.debug("error_recovery: set policy for %s", error_type)

    def get_policy(self, error_type: str) -> RecoveryPolicy:
        """الحصول على سياسة خطأ معين."""
        return self._policies.get(error_type, self._default_policy)

    def register_fallback(self, error_type: str, handler: Callable[[ErrorContext], Any]) -> None:
        """تسجيل معالج fallback."""
        self._fallback_handlers[error_type] = handler
        logger.debug("error_recovery: registered fallback for %s", error_type)

    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        error_type: str = "general",
        context: Optional[Dict[str, Any]] = None,
        policy: Optional[RecoveryPolicy] = None,
    ) -> T:
        """تنفيذ عملية مع إعادة المحاولة."""
        policy = policy or self.get_policy(error_type)
        attempt = 0
        last_error: Optional[Exception] = None
        
        error_context = ErrorContext(
            error_id=str(uuid.uuid4()),
            error_type=error_type,
            error_message="",
            timestamp=time.time(),
            severity=ErrorSeverity.MEDIUM,
            context_data=context or {},
        )
        
        while attempt <= policy.max_retries:
            try:
                result = operation()
                if asyncio.iscoroutine(result):
                    result = await result
                return result
                
            except Exception as e:
                last_error = e
                error_context.error_message = str(e)
                error_context.stack_trace = traceback.format_exc()
                
                await self._record_error(error_context)
                
                if attempt >= policy.max_retries:
                    logger.error(
                        "error_recovery: max retries exhausted error_type=%s",
                        error_type
                    )
                    break
                
                # حساب التأخير
                delay = RetryStrategy.exponential_backoff(
                    attempt,
                    policy.retry_delay_seconds,
                    policy.max_delay_seconds,
                    policy.jitter,
                )
                
                logger.warning(
                    "error_recovery: retrying attempt=%d/%d delay=%.2f error=%s",
                    attempt + 1, policy.max_retries, delay, str(e)
                )
                
                await asyncio.sleep(delay)
                attempt += 1
                
                # إضافة للخطأ السابق
                error_context.previous_errors.append({
                    "attempt": attempt,
                    "error": str(e),
                    "timestamp": time.time(),
                })
        
        # محاولة Fallback
        if policy.fallback_enabled and error_type in self._fallback_handlers:
            try:
                fallback_handler = self._fallback_handlers[error_type]
                fallback_result = fallback_handler(error_context)
                if asyncio.iscoroutine(fallback_result):
                    fallback_result = await fallback_result
                logger.info("error_recovery: fallback succeeded for %s", error_type)
                return fallback_result
            except Exception as fallback_error:
                logger.error(
                    "error_recovery: fallback failed error_type=%s error=%s",
                    error_type, str(fallback_error)
                )
        
        if policy.skip_on_retry_exhausted:
            logger.warning("error_recovery: skipping failed operation")
            return None
        
        raise last_error

    async def execute_safe(
        self,
        operation: Callable[[], T],
        fallback_value: Optional[T] = None,
        error_handler: Optional[Callable[[Exception], None]] = None,
    ) -> Optional[T]:
        """تنفيذ آمن بدون إعادة المحاولة."""
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            if error_handler:
                error_handler(e)
            logger.error("error_recovery: operation failed error=%s", str(e))
            return fallback_value

    async def recover_with_fallback(
        self,
        primary: Callable[[], T],
        fallback: Callable[[ErrorContext], T],
        error_type: str = "general",
    ) -> RecoveryResult:
        """التنفيذ مع fallback."""
        start_time = time.time()
        attempts = 0
        result: Optional[T] = None
        action_taken = RecoveryAction.RETRY
        
        error_context = ErrorContext(
            error_id=str(uuid.uuid4()),
            error_type=error_type,
            error_message="",
            timestamp=start_time,
            severity=ErrorSeverity.MEDIUM,
        )
        
        try:
            result = primary()
            if asyncio.iscoroutine(result):
                result = await result
            return RecoveryResult(
                success=True,
                action_taken=RecoveryAction.RETRY,
                recovered=True,
                attempts=1,
                total_duration_ms=(time.time() - start_time) * 1000,
            )
            
        except Exception as e:
            attempts = 1
            error_context.error_message = str(e)
            await self._record_error(error_context)
            
            # محاولة Fallback
            try:
                fallback_result = fallback(error_context)
                if asyncio.iscoroutine(fallback_result):
                    fallback_result = await fallback_result
                action_taken = RecoveryAction.FALLBACK
                return RecoveryResult(
                    success=True,
                    action_taken=action_taken,
                    recovered=True,
                    attempts=attempts,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    fallback_result=fallback_result,
                )
            except Exception as fallback_error:
                logger.error(
                    "error_recovery: fallback failed error=%s",
                    str(fallback_error)
                )
                return RecoveryResult(
                    success=False,
                    action_taken=RecoveryAction.ABORT,
                    recovered=False,
                    attempts=attempts,
                    total_duration_ms=(time.time() - start_time) * 1000,
                    error_message=str(e),
                )

    async def _record_error(self, error_context: ErrorContext) -> None:
        """تسجيل خطأ."""
        async with self._lock:
            self._error_history.append(error_context)
            if len(self._error_history) > self._max_history:
                self._error_history.pop(0)

    def get_error_history(
        self,
        error_type: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[ErrorContext]:
        """الحصول على تاريخ الأخطاء."""
        errors = self._error_history
        
        if error_type:
            errors = [e for e in errors if e.error_type == error_type]
        
        if since:
            errors = [e for e in errors if e.timestamp >= since]
        
        return errors[-limit:]

    def get_error_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الأخطاء."""
        if not self._error_history:
            return {
                "total_errors": 0,
                "errors_by_type": {},
                "errors_by_severity": {},
                "avg_errors_per_hour": 0.0,
            }
        
        by_type: Dict[str, int] = defaultdict(int)
        by_severity: Dict[str, int] = defaultdict(int)
        
        for error in self._error_history:
            by_type[error.error_type] += 1
            by_severity[error.severity.value] += 1
        
        # حساب متوسط الأخطاء في الساعة
        now = time.time()
        time_range = max(now - self._error_history[0].timestamp, 1)
        errors_per_hour = len(self._error_history) / (time_range / 3600)
        
        return {
            "total_errors": len(self._error_history),
            "errors_by_type": dict(by_type),
            "errors_by_severity": dict(by_severity),
            "avg_errors_per_hour": errors_per_hour,
        }

    def clear_history(self) -> None:
        """مسح تاريخ الأخطاء."""
        self._error_history.clear()
        logger.info("error_recovery: history cleared")


import traceback


# Singleton instance
_error_recovery_manager: Optional[ErrorRecoveryManager] = None


def get_error_recovery_manager() -> ErrorRecoveryManager:
    """الحصول على مدير استرداد الأخطاء الوحيد."""
    global _error_recovery_manager
    if _error_recovery_manager is None:
        _error_recovery_manager = ErrorRecoveryManager()
    return _error_recovery_manager


# Circuit breaker pattern
class CircuitState(str, Enum):
    """حالة Circuit Breaker."""
    CLOSED = "closed"     # طبيعي - يعمل
    OPEN = "open"        # مقطوع - لا يسمح بالتنفيذ
    HALF_OPEN = "half_open"  # نصف مفتوح - اختبار


@dataclass
class CircuitBreakerConfig:
    """إعدادات Circuit Breaker."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    half_open_max_calls: int = 3


class CircuitBreaker:
    """
    نمط Circuit Breaker لمنع الأخطاء المتتالية.
    
    الحالات:
    - CLOSED: يعمل بشكل طبيعي
    - OPEN: لا يسمح بالتنفيذ بعد فشل متتالي
    - HALF_OPEN: يسمح بعدد محدود من المحاولات
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> None:
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """الحصول على الحالة الحالية."""
        return self._state

    def is_available(self) -> bool:
        """التحقق من إمكانية التنفيذ."""
        if self._state == CircuitState.CLOSED:
            return True
        
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._config.timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    return True
            return False
        
        if self._state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._config.half_open_max_calls
        
        return False

    async def call(self, operation: Callable[[], T]) -> T:
        """تنفيذ العملية مع Circuit Breaker."""
        if not self.is_available():
            raise CircuitBreakerOpenError(f"Circuit breaker {self._name} is open")
        
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
        
        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """معالجة النجاح."""
        async with self._lock:
            self._failure_count = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    logger.info("circuit_breaker[%s]: closed", self._name)

    async def _on_failure(self) -> None:
        """معالجة الفشل."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("circuit_breaker[%s]: opened after half_open failure", self._name)
            
            elif self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker[%s]: opened after %d failures",
                    self._name, self._failure_count
                )

    def get_stats(self) -> Dict[str, Any]:
        """الحصول على الإحصائيات."""
        return {
            "name": self._name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "half_open_calls": self._half_open_calls,
            "last_failure_time": self._last_failure_time,
        }

    async def reset(self) -> None:
        """إعادة تعيين Circuit Breaker."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            self._last_failure_time = None
        logger.info("circuit_breaker[%s]: reset", self._name)


class CircuitBreakerOpenError(Exception):
    """خطأ عند فتح Circuit Breaker."""
    pass


class CircuitBreakerRegistry:
    """سجل Circuit Breakers."""

    def __init__(self) -> None:
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """الحصول على أو إنشاء Circuit Breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """الحصول على جميع Circuit Breakers."""
        return {name: cb.get_stats() for name, cb in self._breakers.items()}
