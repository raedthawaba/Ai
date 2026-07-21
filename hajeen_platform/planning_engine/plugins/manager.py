"""Planning Engine - Plugin Architecture System."""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import structlog

logger = structlog.get_logger(__name__)


class PluginState(str, Enum):
    """حالة البرنامج المساعد."""
    DISCOVERED = "discovered"
    LOADING = "loading"
    LOADED = "loaded"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    UNLOADED = "unloaded"


class PluginHook(str, Enum):
    """خطافات البرنامج المساعد."""
    ON_LOAD = "on_load"
    ON_UNLOAD = "on_unload"
    ON_ENABLE = "on_enable"
    ON_DISABLE = "on_disable"
    ON_BEFORE_PLAN = "on_before_plan"
    ON_AFTER_PLAN = "on_after_plan"
    ON_PLAN_ERROR = "on_plan_error"
    ON_STEP_START = "on_step_start"
    ON_STEP_COMPLETE = "on_step_complete"
    ON_STEP_ERROR = "on_step_error"


@dataclass
class PluginMetadata:
    """بيانات البرنامج المساعد."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry_point: str = "main"
    dependencies: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plugin:
    """البرنامج المساعد."""
    plugin_id: str
    metadata: PluginMetadata
    state: PluginState
    module: Optional[Any] = None
    instance: Optional[Any] = None
    loaded_at: Optional[datetime] = None
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    metadata_extra: Dict[str, Any] = field(default_factory=dict)


class PluginInterface(ABC):
    """الواجهة الأساسية للبرنامج المساعد."""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """الحصول على البيانات."""
        ...

    @abstractmethod
    async def on_load(self, config: Dict[str, Any]) -> None:
        """عند التحميل."""
        ...

    @abstractmethod
    async def on_unload(self) -> None:
        """عند إلغاء التحميل."""
        ...

    async def on_enable(self) -> None:
        """عند التمكين."""
        pass

    async def on_disable(self) -> None:
        """عند التعطيل."""
        pass

    async def on_before_plan(self, plan: Any) -> None:
        """قبل تنفيذ الخطة."""
        pass

    async def on_after_plan(self, plan: Any, result: Any) -> None:
        """بعد تنفيذ الخطة."""
        pass

    async def on_plan_error(self, plan: Any, error: Exception) -> None:
        """عند حدوث خطأ في الخطة."""
        pass


class PluginManager:
    """
    مدير البرامج المساعدة.
    
    الميزات:
    - اكتشاف تلقائي للـ plugins
    - تحميل/إلغاء تحميل
    - تمكين/تعطيل
    - خطافات (hooks)
    - إدارة التبعيات
    - عزل الأخطاء
    """

    def __init__(
        self,
        plugin_paths: Optional[List[Path]] = None,
        auto_discover: bool = True,
    ) -> None:
        self._plugin_paths = plugin_paths or [Path.cwd() / "plugins"]
        self._auto_discover = auto_discover
        self._plugins: Dict[str, Plugin] = {}
        self._hooks: Dict[PluginHook, List[Callable]] = {}
        self._enabled_plugins: List[str] = []
        self._lock = asyncio.Lock()
        self._discovered_paths: Dict[str, Path] = {}

    async def discover_plugins(self) -> List[Plugin]:
        """اكتشاف البرامج المساعدة."""
        discovered: List[Plugin] = []
        
        for plugin_path in self._plugin_paths:
            if not plugin_path.exists():
                continue
            
            if plugin_path.is_file():
                await self._discover_from_file(plugin_path, discovered)
            else:
                await self._discover_from_directory(plugin_path, discovered)
        
        logger.info("plugins: discovered %d plugins", len(discovered))
        return discovered

    async def _discover_from_file(self, path: Path, discovered: List[Plugin]) -> None:
        """اكتشاف من ملف."""
        if path.suffix in (".py", ".pyc"):
            try:
                module_name = path.stem
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "PLUGIN_METADATA"):
                        plugin = self._create_plugin_from_metadata(
                            module.PLUGIN_METADATA, module
                        )
                        discovered.append(plugin)
                        self._discovered_paths[plugin.metadata.name] = path
                        
            except Exception as e:
                logger.error("plugins: failed to discover from %s: %s", path, str(e))

    async def _discover_from_directory(self, path: Path, discovered: List[Plugin]) -> None:
        """اكتشاف من مجلد."""
        for item in path.iterdir():
            if item.is_file() and item.suffix == ".py":
                await self._discover_from_file(item, discovered)
            elif item.is_dir() and (item / "__init__.py").exists():
                try:
                    module = importlib.import_module(f"{item.parent.name}.{item.name}")
                    
                    if hasattr(module, "PLUGIN_METADATA"):
                        plugin = self._create_plugin_from_metadata(
                            module.PLUGIN_METADATA, module
                        )
                        discovered.append(plugin)
                        self._discovered_paths[plugin.metadata.name] = item
                        
                except Exception as e:
                    logger.error("plugins: failed to import %s: %s", item, str(e))

    def _create_plugin_from_metadata(self, metadata: Dict, module: Any) -> Plugin:
        """إنشاء plugin من البيانات."""
        plugin_metadata = PluginMetadata(
            name=metadata["name"],
            version=metadata.get("version", "1.0.0"),
            description=metadata.get("description", ""),
            author=metadata.get("author", ""),
            entry_point=metadata.get("entry_point", "main"),
            dependencies=metadata.get("dependencies", []),
            config_schema=metadata.get("config_schema", {}),
        )
        
        plugin = Plugin(
            plugin_id=metadata["name"],
            metadata=plugin_metadata,
            state=PluginState.DISCOVERED,
            module=module,
        )
        
        return plugin

    async def load_plugin(self, plugin_id: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """تحميل برنامج مساعد."""
        async with self._lock:
            if plugin_id in self._plugins:
                logger.warning("plugins: already loaded %s", plugin_id)
                return True
            
            if plugin_id not in self._discovered_paths:
                logger.error("plugins: not discovered %s", plugin_id)
                return False
            
            plugin = self._plugins.get(plugin_id)
            if not plugin:
                logger.error("plugins: not found %s", plugin_id)
                return False
            
            try:
                plugin.state = PluginState.LOADING
                
                # إنشاء المثيل
                if hasattr(plugin.module, plugin.metadata.entry_point):
                    entry = getattr(plugin.module, plugin.metadata.entry_point)
                    if callable(entry):
                        plugin.instance = entry()
                    else:
                        plugin.instance = entry
                
                if plugin.instance and isinstance(plugin.instance, PluginInterface):
                    plugin.state = PluginState.INITIALIZING
                    await plugin.instance.on_load(config or {})
                
                plugin.state = PluginState.LOADED
                plugin.loaded_at = datetime.utcnow()
                plugin.config = config or {}
                
                logger.info("plugins: loaded %s", plugin_id)
                return True
                
            except Exception as e:
                plugin.state = PluginState.ERROR
                plugin.error_message = str(e)
                logger.error("plugins: failed to load %s: %s", plugin_id, str(e))
                return False

    async def unload_plugin(self, plugin_id: str) -> bool:
        """إلغاء تحميل برنامج مساعد."""
        async with self._lock:
            plugin = self._plugins.get(plugin_id)
            if not plugin:
                return False
            
            try:
                if plugin.instance and isinstance(plugin.instance, PluginInterface):
                    await plugin.instance.on_unload()
                
                plugin.state = PluginState.UNLOADED
                plugin.instance = None
                self._enabled_plugins = [p for p in self._enabled_plugins if p != plugin_id]
                
                logger.info("plugins: unloaded %s", plugin_id)
                return True
                
            except Exception as e:
                logger.error("plugins: failed to unload %s: %s", plugin_id, str(e))
                return False

    async def enable_plugin(self, plugin_id: str) -> bool:
        """تمكين برنامج مساعد."""
        async with self._lock:
            plugin = self._plugins.get(plugin_id)
            if not plugin:
                logger.error("plugins: not found %s", plugin_id)
                return False
            
            if plugin.state not in (PluginState.LOADED, PluginState.INACTIVE):
                logger.error("plugins: cannot enable %s (state=%s)", plugin_id, plugin.state)
                return False
            
            try:
                if plugin.instance and isinstance(plugin.instance, PluginInterface):
                    await plugin.instance.on_enable()
                
                plugin.state = PluginState.ACTIVE
                plugin.enabled = True
                if plugin_id not in self._enabled_plugins:
                    self._enabled_plugins.append(plugin_id)
                
                logger.info("plugins: enabled %s", plugin_id)
                return True
                
            except Exception as e:
                logger.error("plugins: failed to enable %s: %s", plugin_id, str(e))
                return False

    async def disable_plugin(self, plugin_id: str) -> bool:
        """تعطيل برنامج مساعد."""
        async with self._lock:
            plugin = self._plugins.get(plugin_id)
            if not plugin:
                return False
            
            try:
                if plugin.instance and isinstance(plugin.instance, PluginInterface):
                    await plugin.instance.on_disable()
                
                plugin.state = PluginState.INACTIVE
                plugin.enabled = False
                self._enabled_plugins = [p for p in self._enabled_plugins if p != plugin_id]
                
                logger.info("plugins: disabled %s", plugin_id)
                return True
                
            except Exception as e:
                logger.error("plugins: failed to disable %s: %s", plugin_id, str(e))
                return False

    def register_hook(self, hook: PluginHook, callback: Callable) -> None:
        """تسجيل خطاف."""
        if hook not in self._hooks:
            self._hooks[hook] = []
        self._hooks[hook].append(callback)
        logger.debug("plugins: registered hook %s", hook)

    def unregister_hook(self, hook: PluginHook, callback: Callable) -> None:
        """إلغاء تسجيل خطاف."""
        if hook in self._hooks and callback in self._hooks[hook]:
            self._hooks[hook].remove(callback)

    async def execute_hooks(self, hook: PluginHook, *args: Any, **kwargs: Any) -> None:
        """تنفيذ الخطافات."""
        if hook not in self._hooks:
            return
        
        for callback in self._hooks[hook]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error("plugins: hook error hook=%s error=%s", hook, str(e))

    def get_plugin(self, plugin_id: str) -> Optional[Plugin]:
        """الحصول على برنامج مساعد."""
        return self._plugins.get(plugin_id)

    def list_plugins(self, state: Optional[PluginState] = None) -> List[Plugin]:
        """قائمة البرامج المساعدة."""
        plugins = list(self._plugins.values())
        if state:
            plugins = [p for p in plugins if p.state == state]
        return plugins

    def list_enabled_plugins(self) -> List[str]:
        """قائمة البرامج المساعدة المفعلة."""
        return self._enabled_plugins.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات."""
        by_state: Dict[str, int] = {}
        for plugin in self._plugins.values():
            state_name = plugin.state.value
            by_state[state_name] = by_state.get(state_name, 0) + 1
        
        return {
            "total_plugins": len(self._plugins),
            "enabled_plugins": len(self._enabled_plugins),
            "by_state": by_state,
            "registered_hooks": {hook.value: len(callbacks) for hook, callbacks in self._hooks.items()},
        }


# Plugin decorator
def plugin(
    name: str,
    version: str,
    description: str = "",
    author: str = "",
    dependencies: Optional[List[str]] = None,
) -> Callable[[Type[PluginInterface]], Type[PluginInterface]]:
    """ديكوريتر لإنشاء plugin."""
    PLUGIN_METADATA = {
        "name": name,
        "version": version,
        "description": description,
        "author": author,
        "dependencies": dependencies or [],
    }
    
    def decorator(cls: Type[PluginInterface]) -> Type[PluginInterface]:
        cls.PLUGIN_METADATA = PLUGIN_METADATA
        return cls
    
    return decorator


# Example plugin
class ExamplePlugin(PluginInterface):
    """مثال على برنامج مساعد."""
    
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="example_plugin",
            version="1.0.0",
            description="An example plugin",
        )
    
    async def on_load(self, config: Dict[str, Any]) -> None:
        logger.info("example_plugin: loaded with config=%s", config)
    
    async def on_unload(self) -> None:
        logger.info("example_plugin: unloaded")


# Singleton instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """الحصول على مدير البرامج المساعدة الوحيد."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
