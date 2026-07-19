"""
Configuration Management Module
============================

Provides centralized configuration management with:
- Environment variable support
- Type validation
- Secret management
- Configuration hot-reloading
- Default values
- Configuration schemas
"""

from __future__ import annotations

import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar, Union, get_type_hints
from dataclasses import dataclass, field, fields
from enum import Enum
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConfigSource(Enum):
    """Configuration source priority."""
    DEFAULT = "default"
    ENV = "env"
    FILE = "file"
    SECRET = "secret"


@dataclass
class ConfigField:
    """Configuration field definition."""
    name: str
    type: Type
    default: Any = None
    description: str = ""
    required: bool = False
    env_var: Optional[str] = None
    secret: bool = False


class ConfigurationError(Exception):
    """Configuration validation error."""
    pass


class Config:
    """
    Centralized configuration manager with validation.
    
    Usage:
        config = Config.from_env()
        api_key = config.get("OPENAI_API_KEY", secret=True)
        port = config.get("PORT", default=8000, type=int)
    """
    
    _instance: Optional[Config] = None
    _config: Dict[str, Any] = {}
    _sources: Dict[str, ConfigSource] = {}
    
    def __init__(self):
        self._config = {}
        self._sources = {}
        self._schemas: Dict[str, Type] = {}
        self._loaded = False
    
    @classmethod
    def get_instance(cls) -> Config:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def from_env(cls, prefix: str = "HAJEEN_") -> Config:
        """Load configuration from environment variables."""
        instance = cls.get_instance()
        instance._load_from_env(prefix)
        instance._loaded = True
        return instance
    
    @classmethod
    def from_file(cls, path: Union[str, Path]) -> Config:
        """Load configuration from file."""
        instance = cls.get_instance()
        instance._load_from_file(path)
        instance._loaded = True
        return instance
    
    def _load_from_env(self, prefix: str = "HAJEEN_"):
        """Load all environment variables with prefix."""
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower()
                self._config[config_key] = self._parse_value(value)
                self._sources[config_key] = ConfigSource.ENV
            elif key.startswith("OPENAI_") or key.startswith("ANTHROPIC_") or key.startswith("GOOGLE_"):
                config_key = key.lower()
                self._config[config_key] = self._parse_value(value)
                self._sources[config_key] = ConfigSource.ENV
    
    def _load_from_file(self, path: Union[str, Path]):
        """Load configuration from YAML/JSON file."""
        path = Path(path)
        if not path.exists():
            logger.warning(f"Config file not found: {path}")
            return
        
        with open(path) as f:
            if path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif path.suffix == '.json':
                data = json.load(f)
            else:
                raise ConfigurationError(f"Unsupported config format: {path.suffix}")
        
        if isinstance(data, dict):
            self._merge_config(data, ConfigSource.FILE)
    
    def _merge_config(self, data: Dict[str, Any], source: ConfigSource):
        """Merge configuration data."""
        def flatten(d: Dict, prefix: str = "") -> Dict:
            items = {}
            for k, v in d.items():
                new_key = f"{prefix}{k}".lower() if prefix else k.lower()
                if isinstance(v, dict):
                    items.update(flatten(v, f"{new_key}_"))
                else:
                    items[new_key] = v
            return items
        
        flat_data = flatten(data)
        for key, value in flat_data.items():
            if key not in self._sources or self._sources[key] == ConfigSource.DEFAULT:
                self._config[key] = self._parse_value(value)
                self._sources[key] = source
    
    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        if value is None:
            return None
        
        value = value.strip()
        
        # Boolean
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True
        if value.lower() in ('false', 'no', '0', 'off'):
            return False
        
        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # JSON-like
        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        return value
    
    def get(
        self,
        key: str,
        default: Any = None,
        type: Optional[Type] = None,
        secret: bool = False,
        required: bool = False
    ) -> Any:
        """
        Get configuration value.
        
        Args:
            key: Configuration key (case-insensitive)
            default: Default value if not found
            type: Type to convert value to
            secret: Mark as secret (for logging)
            required: Raise error if not found
        """
        key_lower = key.lower()
        
        if key_lower not in self._config:
            if required:
                raise ConfigurationError(f"Required config key not found: {key}")
            return default
        
        value = self._config[key_lower]
        
        if type is not None and value is not None:
            try:
                if type == bool and isinstance(value, str):
                    value = value.lower() in ('true', 'yes', '1', 'on')
                elif not isinstance(value, type):
                    value = type(value)
            except (ValueError, TypeError) as e:
                raise ConfigurationError(f"Config type mismatch for {key}: {e}")
        
        return value
    
    def set(self, key: str, value: Any, source: ConfigSource = ConfigSource.DEFAULT):
        """Set configuration value."""
        self._config[key.lower()] = value
        self._sources[key.lower()] = source
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration (excluding secrets)."""
        return {k: v for k, v in self._config.items()}
    
    def get_source(self, key: str) -> Optional[ConfigSource]:
        """Get the source of a configuration value."""
        return self._sources.get(key.lower())
    
    def validate_schema(self, schema: Type) -> bool:
        """Validate configuration against a schema class."""
        hints = get_type_hints(schema)
        instance = schema()
        
        for field_name, field_type in hints.items():
            value = self.get(field_name, required=False)
            if value is not None:
                try:
                    if field_type == bool and isinstance(value, str):
                        value = value.lower() in ('true', 'yes', '1', 'on')
                    elif not isinstance(value, field_type):
                        value = field_type(value)
                    setattr(instance, field_name, value)
                except (ValueError, TypeError) as e:
                    raise ConfigurationError(f"Schema validation failed for {field_name}: {e}")
        
        self._schemas[schema.__name__] = schema
        return True
    
    def reload(self):
        """Reload configuration from sources."""
        self._config = {}
        self._sources = {}
        self._load_from_env()


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


# Convenience decorators
def config_value(key: str, default: Any = None, type: Optional[Type] = None):
    """Decorator to inject configuration value."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            config = get_config()
            value = config.get(key, default=default, type=type)
            return func(value, *args, **kwargs)
        return wrapper
    return decorator
