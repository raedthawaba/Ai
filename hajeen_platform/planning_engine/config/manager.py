"""Planning Engine Configuration System."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ConfigFormat(str, Enum):
    """صيغ الملفات المدعومة."""
    YAML = "yaml"
    JSON = "json"
    ENV = "env"
    AUTO = "auto"


@dataclass
class ConfigSource:
    """مصدر إعدادات واحد."""
    name: str
    format: ConfigFormat
    path: Optional[Path] = None
    data: Optional[Dict[str, Any]] = None
    priority: int = 0
    loaded_at: Optional[datetime] = None


@dataclass
class ConfigSchema:
    """مخطط الإعدادات - يحدد القيم المطلوبة والافتراضية."""
    engine: Dict[str, Any] = field(default_factory=lambda: {
        "max_concurrent_steps": 10,
        "default_timeout_seconds": 60.0,
        "default_max_retries": 3,
        "enable_parallel_execution": True,
        "enable_step_caching": False,
        "cache_ttl_seconds": 300.0,
    })
    logging: Dict[str, Any] = field(default_factory=lambda: {
        "level": "INFO",
        "format": "json",
        "output_dir": "logs",
        "max_file_size_mb": 50,
        "backup_count": 5,
    })
    metrics: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "port": 9090,
        "path": "/metrics",
        "collection_interval_seconds": 10,
    })
    error_recovery: Dict[str, Any] = field(default_factory=lambda: {
        "max_retries": 3,
        "retry_delay_seconds": 1.0,
        "exponential_backoff": True,
        "max_delay_seconds": 60.0,
    })
    plugins: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "auto_discover": True,
        "paths": ["plugins"],
        "blacklist": [],
    })


class ConfigurationManager:
    """
    مدير الإعدادات المركزي.
    
    الميزات:
    - تحميل من مصادر متعددة (YAML, JSON, ENV)
    - دمج الإعدادات بأولويات
    - التحقق من الصحة
    - إعادة تحميل الإعدادات
    - دعم القيم السرية
    """

    def __init__(self) -> None:
        self._sources: List[ConfigSource] = []
        self._config: Dict[str, Any] = {}
        self._secrets: Dict[str, str] = {}
        self._schema = ConfigSchema()
        self._loaded = False
        self._listeners: List[callable] = []

    def add_source(
        self,
        name: str,
        format: ConfigFormat,
        path: Optional[Path] = None,
        data: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ) -> None:
        """إضافة مصدر إعدادات."""
        source = ConfigSource(
            name=name,
            format=format,
            path=path,
            data=data,
            priority=priority,
        )
        self._sources.append(source)
        self._sources.sort(key=lambda s: s.priority)
        logger.debug("config: added source=%s priority=%d", name, priority)

    def load(self, auto_discover: bool = True) -> Dict[str, Any]:
        """تحميل جميع المصادر ودمج الإعدادات."""
        if self._loaded and self._config:
            return self._config
        
        merged: Dict[str, Any] = {}
        
        # تطبيق الإعدادات الافتراضية أولاً
        default_config = self._schema_to_dict()
        merged = self._deep_merge(merged, default_config)
        
        # تحميل من المصادر
        for source in self._sources:
            try:
                if source.data:
                    config_data = source.data
                elif source.path and source.path.exists():
                    config_data = self._load_from_path(source.path, source.format)
                else:
                    continue
                
                config_data = self._resolve_env_vars(config_data)
                config_data = self._resolve_secrets(config_data)
                merged = self._deep_merge(merged, config_data)
                source.loaded_at = datetime.utcnow()
                
                logger.info("config: loaded source=%s", source.name)
                
            except Exception as e:
                logger.error("config: failed to load source=%s error=%s", source.name, str(e))
        
        # اكتشاف تلقائي للملفات
        if auto_discover:
            self._auto_discover()
        
        self._config = merged
        self._loaded = True
        
        logger.info("config: loaded total_sources=%d", len(self._sources))
        return self._config

    def _auto_discover(self) -> None:
        """اكتشاف تلقائي لملفات الإعدادات."""
        search_paths = [
            Path.cwd(),
            Path.cwd() / "config",
            Path(__file__).parent.parent.parent / "configs",
        ]
        
        patterns = {
            "planning_engine.yaml": ConfigFormat.YAML,
            "planning_engine.yml": ConfigFormat.YAML,
            "planning_engine.json": ConfigFormat.JSON,
            ".env": ConfigFormat.ENV,
        }
        
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            for filename, fmt in patterns.items():
                config_file = search_path / filename
                if config_file.exists():
                    existing = [s for s in self._sources if s.name == filename]
                    if not existing:
                        self.add_source(
                            name=filename,
                            format=fmt,
                            path=config_file,
                            priority=50,
                        )
                        config_data = self._load_from_path(config_file, fmt)
                        self._config = self._deep_merge(self._config, config_data)
                        logger.info("config: auto-discovered %s", config_file)

    def _load_from_path(self, path: Path, fmt: ConfigFormat) -> Dict[str, Any]:
        """تحميل إعدادات من ملف."""
        if fmt == ConfigFormat.AUTO:
            fmt = self._detect_format(path)
        
        content = path.read_text(encoding="utf-8")
        
        if fmt == ConfigFormat.YAML:
            return yaml.safe_load(content) or {}
        elif fmt == ConfigFormat.JSON:
            return json.loads(content)
        elif fmt == ConfigFormat.ENV:
            return self._parse_env_file(content)
        else:
            return {}

    def _detect_format(self, path: Path) -> ConfigFormat:
        """اكتشاف صيغة الملف."""
        ext = path.suffix.lower()
        if ext in (".yaml", ".yml"):
            return ConfigFormat.YAML
        elif ext == ".json":
            return ConfigFormat.JSON
        elif ext == ".env":
            return ConfigFormat.ENV
        return ConfigFormat.YAML

    def _parse_env_file(self, content: str) -> Dict[str, Any]:
        """تحليل ملف .env."""
        config: Dict[str, Any] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
        return config

    def _resolve_env_vars(self, config: Any) -> Any:
        """استبدال متغيرات البيئة."""
        if isinstance(config, str):
            if config.startswith("${") and config.endswith("}"):
                env_var = config[2:-1]
                default = None
                if ":" in env_var:
                    env_var, default = env_var.split(":", 1)
                return os.getenv(env_var, default)
            return config
        elif isinstance(config, dict):
            return {k: self._resolve_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_env_vars(item) for item in config]
        return config

    def _resolve_secrets(self, config: Any) -> Any:
        """استبدال القيم السرية."""
        if isinstance(config, str):
            if config.startswith("secret:") and config.endswith("}"):
                key = config[8:-1]
                return self._secrets.get(key, config)
            return config
        elif isinstance(config, dict):
            return {k: self._resolve_secrets(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_secrets(item) for item in config]
        return config

    def _schema_to_dict(self) -> Dict[str, Any]:
        """تحويل المخطط إلى قاموس."""
        return {
            "engine": self._schema.engine,
            "logging": self._schema.logging,
            "metrics": self._schema.metrics,
            "error_recovery": self._schema.error_recovery,
            "plugins": self._schema.plugins,
        }

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """دمج عميق لقواميسين."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            elif value is not None:
                result[key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """الحصول على قيمة إعداد."""
        if not self._loaded:
            self.load()
        
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value

    def set(self, key: str, value: Any) -> None:
        """تعيين قيمة إعداد."""
        keys = key.split(".")
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        self._notify_listeners(key, value)

    def set_secret(self, key: str, value: str) -> None:
        """تعيين قيمة سرية."""
        self._secrets[key] = value
        logger.debug("config: secret set key=%s", key)

    def get_all(self) -> Dict[str, Any]:
        """الحصول على جميع الإعدادات."""
        if not self._loaded:
            self.load()
        return self._config.copy()

    def reload(self) -> Dict[str, Any]:
        """إعادة تحميل الإعدادات."""
        self._loaded = False
        self._sources = [s for s in self._sources if s.priority < 50]
        return self.load()

    def add_listener(self, listener: callable) -> None:
        """إضافة مستمع للتغييرات."""
        self._listeners.append(listener)

    def remove_listener(self, listener: callable) -> None:
        """إزالة مستمع."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self, key: str, value: Any) -> None:
        """إشعار المستمعين بالتغييرات."""
        for listener in self._listeners:
            try:
                listener(key, value)
            except Exception as e:
                logger.error("config: listener error=%s", str(e))

    def validate(self) -> List[str]:
        """التحقق من صحة الإعدادات."""
        errors: List[str] = []
        
        # التحقق من القيم المطلوبة
        required = {
            "engine.max_concurrent_steps": int,
            "logging.level": str,
        }
        
        for key, expected_type in required.items():
            value = self.get(key)
            if value is None:
                errors.append(f"Missing required config: {key}")
            elif not isinstance(value, expected_type):
                errors.append(f"Invalid type for {key}: expected {expected_type.__name__}")
        
        return errors

    def export(self, path: Path, format: ConfigFormat = ConfigFormat.YAML) -> None:
        """تصدير الإعدادات إلى ملف."""
        if not self._loaded:
            self.load()
        
        content: str
        if format == ConfigFormat.YAML:
            content = yaml.dump(self._config, default_flow_style=False, allow_unicode=True)
        elif format == ConfigFormat.JSON:
            content = json.dumps(self._config, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        path.write_text(content, encoding="utf-8")
        logger.info("config: exported to %s", path)


# Singleton instance
_config_manager: Optional[ConfigurationManager] = None


def get_config() -> ConfigurationManager:
    """الحصول على مدير الإعدادات الوحيد."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager()
    return _config_manager
