"""Planning Engine - Structured Logging System."""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

# Context variables للـ correlation IDs
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_request_id: ContextVar[str] = ContextVar("request_id", default="")
_plan_id: ContextVar[str] = ContextVar("plan_id", default="")
_pipeline_id: ContextVar[str] = ContextVar("pipeline_id", default="")


def set_correlation_id(cid: str) -> None:
    """تعيين Correlation ID."""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    """الحصول على Correlation ID."""
    result = _correlation_id.get()
    if not result:
        result = str(uuid.uuid4())[:8]
        _correlation_id.set(result)
    return result


def set_request_id(rid: str) -> None:
    """تعيين Request ID."""
    _request_id.set(rid)


def get_request_id() -> str:
    """الحصول على Request ID."""
    return _request_id.get()


def set_plan_id(pid: str) -> None:
    """تعيين Plan ID."""
    _plan_id.set(pid)


def get_plan_id() -> str:
    """الحصول على Plan ID."""
    return _plan_id.get()


def set_pipeline_id(pid: str) -> None:
    """تعيين Pipeline ID."""
    _pipeline_id.set(pid)


def get_pipeline_id() -> str:
    """الحصول على Pipeline ID."""
    return _pipeline_id.get()


class StructuredFormatter(logging.Formatter):
    """مُنسق لتسجيل logs كـ JSON."""

    SERVICE_NAME = os.getenv("SERVICE_NAME", "planning-engine")
    ENV = os.getenv("ENV", "development")

    def format(self, record: logging.LogRecord) -> str:
        exc_info_str: Optional[str] = None
        if record.exc_info:
            exc_info_str = "".join(traceback.format_exception(*record.exc_info))

        entry: Dict[str, Any] = {
            "timestamp": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                + f".{int((record.created % 1) * 1000):03d}Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.SERVICE_NAME,
            "env": self.ENV,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Context fields
        cid = get_correlation_id()
        if cid:
            entry["correlation_id"] = cid
        rid = get_request_id()
        if rid:
            entry["request_id"] = rid
        pid = get_plan_id()
        if pid:
            entry["plan_id"] = pid
        plid = get_pipeline_id()
        if plid:
            entry["pipeline_id"] = plid

        # Exception
        if exc_info_str:
            entry["exception"] = exc_info_str.strip()

        # Extra fields
        skip_keys = {
            "msg", "args", "created", "exc_info", "exc_text", "filename",
            "funcName", "id", "levelname", "levelno", "lineno", "message",
            "module", "msecs", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "thread", "threadName",
        }
        for k, v in record.__dict__.items():
            if k not in skip_keys and not k.startswith("_"):
                try:
                    json.dumps(v)
                    entry[k] = v
                except (TypeError, ValueError):
                    entry[k] = str(v)

        return json.dumps(entry, ensure_ascii=False)


class AuditLogger:
    """مسجل أحداث التدقيق."""

    def __init__(self, audit_log_path: str = "logs/audit.jsonl") -> None:
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        self._path = audit_log_path
        self._logger = logging.getLogger("planning_engine.audit")

    def log(
        self,
        event: str,
        actor: str,
        resource: str,
        outcome: str = "success",
        **extra: Any,
    ) -> None:
        """تسجيل حدث تدقيق."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "actor": actor,
            "resource": resource,
            "outcome": outcome,
            "correlation_id": get_correlation_id(),
            **extra,
        }
        self._logger.info("AUDIT", extra=entry)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass


def configure_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 5,
    json_console: bool = True,
    json_file: bool = True,
) -> None:
    """تهيئة نظام التسجيل المُهيكل."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # تهيئة structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(serializer=json.dumps),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = StructuredFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        formatter if json_console else logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
        )
    )
    root.addHandler(console)

    if json_file:
        # Rotating file handler — general
        file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "planning_engine.jsonl"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        # Error file handler
        error_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(log_dir, "planning_engine_errors.jsonl"),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root.addHandler(error_handler)

    # Pipeline-specific logger
    pipeline_logger = logging.getLogger("planning_engine.pipeline")
    pipeline_file = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "pipelines.jsonl"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    pipeline_file.setFormatter(formatter)
    pipeline_logger.addHandler(pipeline_file)

    logging.getLogger("planning_engine").info(
        "Logging configured: level=%s dir=%s", level, log_dir
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """الحصول على مسجل."""
    return structlog.get_logger(name)


def get_audit_logger() -> AuditLogger:
    """الحصول على مسجل التدقيق."""
    return AuditLogger()


# Singleton audit logger
_audit: Optional[AuditLogger] = None


def get_audit_logger_singleton() -> AuditLogger:
    """الحصول على مثيل وحيد لمسجل التدقيق."""
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit


class LogContext:
    """مدير سياق التسجيل."""

    def __init__(self, **context: Any) -> None:
        self._context = context
        self._tokens = []

    def __enter__(self) -> LogContext:
        for key, value in self._context.items():
            token = structlog.contextvars.bind_contextvars(**{key: str(value)})
            self._tokens.append(token)
        return self

    def __exit__(self, *args: Any) -> None:
        for token in self._tokens:
            structlog.contextvars.unbind_contextvars(*self._context.keys())


class PerformanceLogger:
    """مسجل الأداء."""

    def __init__(self, logger: Optional[structlog.BoundLogger] = None) -> None:
        self._logger = logger or get_logger("performance")
        self._timings: Dict[str, float] = {}

    def start(self, operation: str) -> None:
        """بدء قياس عملية."""
        self._timings[operation] = time.time()

    def end(self, operation: str, **kwargs: Any) -> float:
        """إنهاء قياس عملية وإرجاع المدة."""
        if operation not in self._timings:
            self._logger.warning("performance: no start time for operation", operation=operation)
            return 0.0
        
        duration_ms = (time.time() - self._timings[operation]) * 1000
        del self._timings[operation]
        
        self._logger.info(
            "performance: operation_completed",
            operation=operation,
            duration_ms=duration_ms,
            **kwargs
        )
        
        return duration_ms

    def measure(self, operation: str) -> float:
        """قياس المدة فقط (بدون تسجيل)."""
        if operation in self._timings:
            return (time.time() - self._timings[operation]) * 1000
        return 0.0


class RequestLogger:
    """مسجل الطلبات مع تتبع كامل."""

    def __init__(self, request_id: Optional[str] = None) -> None:
        self._request_id = request_id or str(uuid.uuid4())
        set_request_id(self._request_id)

    def log_request_start(self, method: str, path: str, **kwargs: Any) -> None:
        """تسجيل بدء طلب."""
        logger = get_logger("http")
        logger.info(
            "request_start",
            request_id=self._request_id,
            method=method,
            path=path,
            **kwargs
        )

    def log_request_end(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **kwargs: Any,
    ) -> None:
        """تسجيل نهاية طلب."""
        logger = get_logger("http")
        level = "info" if status_code < 400 else "warning"
        getattr(logger, level)(
            "request_end",
            request_id=self._request_id,
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs
        )

    def get_request_id(self) -> str:
        """الحصول على معرف الطلب."""
        return self._request_id
