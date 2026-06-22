"""Structured JSON Logger — Phase 6 — logging مُهيكل مع correlation IDs."""
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

# Context variable للـ correlation ID عبر async calls
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_request_id: ContextVar[str] = ContextVar("request_id", default="")
_pipeline_id: ContextVar[str] = ContextVar("pipeline_id", default="")


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    return _correlation_id.get() or str(uuid.uuid4())[:8]


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> str:
    return _request_id.get()


def set_pipeline_id(pid: str) -> None:
    _pipeline_id.set(pid)


def get_pipeline_id() -> str:
    return _pipeline_id.get()


class StructuredFormatter(logging.Formatter):
    """يُنسّق log records كـ JSON strings."""

    SERVICE_NAME = os.getenv("SERVICE_NAME", "hajeen-platform")
    ENV = os.getenv("ENV", "development")

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        exc_info_str: Optional[str] = None
        if record.exc_info:
            exc_info_str = "".join(traceback.format_exception(*record.exc_info))

        entry: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int((record.created % 1) * 1000):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.SERVICE_NAME,
            "env": self.ENV,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Context fields
        cid = get_correlation_id()
        if cid:
            entry["correlation_id"] = cid
        rid = get_request_id()
        if rid:
            entry["request_id"] = rid
        pid = get_pipeline_id()
        if pid:
            entry["pipeline_id"] = pid

        # Exception
        if exc_info_str:
            entry["exception"] = exc_info_str.strip()

        # Extra fields من الـ record
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
    """Audit logger منفصل لتسجيل الأحداث الحرجة."""

    def __init__(self, audit_log_path: str = "logs/audit.jsonl") -> None:
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        self._path = audit_log_path
        self._logger = logging.getLogger("hajeen.audit")

    def log(
        self,
        event: str,
        actor: str,
        resource: str,
        outcome: str = "success",
        **extra: Any,
    ) -> None:
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
) -> None:
    """تهيئة نظام الـ logging المُهيكل مع rotating file handlers."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = StructuredFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter if json_console else logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    ))
    root.addHandler(console)

    # Rotating file handler — general
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "app.jsonl"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "error.jsonl"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    logging.getLogger("hajeen").info(
        "Structured logging configured: level=%s dir=%s", level, log_dir
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"hajeen.{name}")


# Singleton audit logger
_audit: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger()
    return _audit
