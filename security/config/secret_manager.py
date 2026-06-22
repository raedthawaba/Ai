"""Secret Manager — Phase 7 — إدارة آمنة للأسرار والمتغيرات."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecretManager:
    """
    إدارة الأسرار والإعدادات مع:
    - تحميل من environment variables
    - validation للإعدادات المطلوبة
    - masking عند الـ logging
    - secure defaults
    - secret rotation hooks
    - audit trail
    """

    # الأسرار المطلوبة في production
    REQUIRED_SECRETS = [
        "JWT_SECRET",
        "DATABASE_URL",
        "SESSION_SECRET",
    ]

    # الأسرار التي يجب إخفاؤها في الـ logs
    SENSITIVE_KEYS = {
        "JWT_SECRET", "DATABASE_URL", "API_KEY", "SESSION_SECRET",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "REDIS_PASSWORD",
        "SMTP_PASSWORD", "S3_SECRET_KEY",
    }

    def __init__(self, env_file: Optional[str] = None) -> None:
        self._secrets: Dict[str, str] = {}
        self._rotation_callbacks: Dict[str, Any] = {}
        self._access_log: List[Dict] = []

        if env_file:
            self._load_env_file(env_file)

        self._load_from_environment()

    def _load_from_environment(self) -> None:
        for key, value in os.environ.items():
            self._secrets[key] = value

    def _load_env_file(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            logger.warning("ملف الإعدادات غير موجود: %s", path)
            return
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    self._secrets[key] = value
                    os.environ.setdefault(key, value)
        logger.info("تُحمّلت الإعدادات من: %s", path)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = self._secrets.get(key) or os.environ.get(key, default)
        self._audit_access(key, found=value is not None)
        return value

    def require(self, key: str) -> str:
        value = self.get(key)
        if not value:
            raise ValueError(
                f"المتغير المطلوب '{key}' غير موجود في البيئة"
            )
        return value

    def _audit_access(self, key: str, found: bool) -> None:
        """تسجيل الوصول للأسرار (بدون القيمة)."""
        import time
        self._access_log.append({
            "key": key,
            "found": found,
            "sensitive": key in self.SENSITIVE_KEYS,
            "timestamp": time.time(),
        })
        if len(self._access_log) > 1000:
            self._access_log = self._access_log[-500:]

    def validate_required(self, env: str = "production") -> List[str]:
        """يتحقق من وجود الأسرار المطلوبة — يُعيد قائمة المفقودة."""
        if env != "production":
            return []
        missing = [k for k in self.REQUIRED_SECRETS if not self.get(k)]
        if missing:
            logger.error("أسرار مفقودة في production: %s", missing)
        return missing

    def mask(self, key: str, value: str) -> str:
        """يُخفي قيمة السر لأغراض الـ logging."""
        if key in self.SENSITIVE_KEYS and value:
            return value[:4] + "****" + value[-2:] if len(value) > 6 else "****"
        return value

    def register_rotation_callback(self, key: str, callback: Any) -> None:
        """تسجيل callback للتشغيل عند تدوير السر."""
        self._rotation_callbacks[key] = callback

    def rotate(self, key: str, new_value: str) -> None:
        """تدوير سر — يُشغّل الـ callback إذا كان مسجّلاً."""
        old_value = self._secrets.get(key)
        self._secrets[key] = new_value
        os.environ[key] = new_value
        cb = self._rotation_callbacks.get(key)
        if cb:
            try:
                cb(old_value, new_value)
            except Exception as exc:
                logger.error("فشل rotation callback لـ '%s': %s", key, exc)
        logger.info("تم تدوير السر: %s", key)

    def summary(self) -> Dict:
        """ملخص غير حساس لحالة الأسرار."""
        present = {k: bool(v) for k, v in self._secrets.items() if k.isupper()}
        return {
            "total_secrets": len(present),
            "required_present": [k for k in self.REQUIRED_SECRETS if self.get(k)],
            "required_missing": [k for k in self.REQUIRED_SECRETS if not self.get(k)],
        }


# Singleton
_manager: Optional[SecretManager] = None


def get_secret_manager(env_file: Optional[str] = None) -> SecretManager:
    global _manager
    if _manager is None:
        _manager = SecretManager(env_file=env_file)
    return _manager


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    return get_secret_manager().get(key, default)
