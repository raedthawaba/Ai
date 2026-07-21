"""Unit tests for Plugin Manager."""
import asyncio
import pytest
from pathlib import Path
import tempfile

from planning_engine.plugins.manager import (
    PluginManager,
    Plugin,
    PluginState,
    PluginHook,
    PluginMetadata,
    PluginInterface,
    get_plugin_manager,
)


class TestPluginMetadata:
    """Tests for PluginMetadata class."""

    def test_create_metadata(self):
        """Test creating metadata."""
        metadata = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            description="A test plugin",
            author="Test Author",
        )
        
        assert metadata.name == "test_plugin"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"


class TestPlugin:
    """Tests for Plugin class."""

    def test_create_plugin(self):
        """Test creating a plugin."""
        metadata = PluginMetadata(name="test", version="1.0.0")
        
        plugin = Plugin(
            plugin_id="test_plugin",
            metadata=metadata,
            state=PluginState.DISCOVERED,
        )
        
        assert plugin.plugin_id == "test_plugin"
        assert plugin.state == PluginState.DISCOVERED
        assert plugin.enabled is True


class TestPluginManager:
    """Tests for PluginManager class."""

    @pytest.fixture
    def manager(self):
        """Create plugin manager instance."""
        return PluginManager()

    @pytest.mark.asyncio
    async def test_create_manager(self, manager):
        """Test manager creation."""
        assert manager is not None
        assert len(manager._plugins) == 0

    @pytest.mark.asyncio
    async def test_discover_plugins_empty(self, manager):
        """Test discovering plugins from empty path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager._plugin_paths = [Path(tmpdir)]
            discovered = await manager.discover_plugins()
            
            assert len(discovered) == 0

    def test_register_hook(self, manager):
        """Test registering hooks."""
        async def my_hook(*args, **kwargs):
            pass
        
        manager.register_hook(PluginHook.ON_LOAD, my_hook)
        
        assert PluginHook.ON_LOAD in manager._hooks
        assert my_hook in manager._hooks[PluginHook.ON_LOAD]

    def test_unregister_hook(self, manager):
        """Test unregistering hooks."""
        async def my_hook(*args, **kwargs):
            pass
        
        manager.register_hook(PluginHook.ON_LOAD, my_hook)
        manager.unregister_hook(PluginHook.ON_LOAD, my_hook)
        
        assert my_hook not in manager._hooks[PluginHook.ON_LOAD]

    @pytest.mark.asyncio
    async def test_execute_hooks(self, manager):
        """Test executing hooks."""
        executed = []
        
        async def my_hook(*args, **kwargs):
            executed.append(True)
        
        manager.register_hook(PluginHook.ON_LOAD, my_hook)
        await manager.execute_hooks(PluginHook.ON_LOAD)
        
        assert len(executed) == 1

    def test_get_plugin(self, manager):
        """Test getting a plugin."""
        metadata = PluginMetadata(name="get_test", version="1.0.0")
        
        manager._plugins["get_test"] = Plugin(
            plugin_id="get_test",
            metadata=metadata,
            state=PluginState.LOADED,
        )
        
        plugin = manager.get_plugin("get_test")
        assert plugin is not None
        assert plugin.metadata.name == "get_test"

    def test_list_plugins(self, manager):
        """Test listing plugins."""
        metadata1 = PluginMetadata(name="list1", version="1.0.0")
        metadata2 = PluginMetadata(name="list2", version="1.0.0")
        
        manager._plugins["list1"] = Plugin("list1", metadata1, PluginState.LOADED)
        manager._plugins["list2"] = Plugin("list2", metadata2, PluginState.DISCOVERED)
        
        all_plugins = manager.list_plugins()
        assert len(all_plugins) == 2
        
        loaded_plugins = manager.list_plugins(state=PluginState.LOADED)
        assert len(loaded_plugins) == 1

    def test_statistics(self, manager):
        """Test getting statistics."""
        metadata = PluginMetadata(name="stats_test", version="1.0.0")
        
        manager._plugins["stats_test"] = Plugin(
            "stats_test", metadata, PluginState.LOADED
        )
        
        stats = manager.get_statistics()
        
        assert stats["total_plugins"] == 1
        assert stats["enabled_plugins"] == 0

    def test_singleton(self):
        """Test singleton pattern."""
        from planning_engine.plugins.manager import _plugin_manager
        
        manager1 = get_plugin_manager()
        manager2 = get_plugin_manager()
        
        assert manager1 is manager2


class TestPluginInterface:
    """Tests for PluginInterface class."""

    def test_create_plugin_implementation(self):
        """Test creating a plugin implementation."""
        class MyPlugin(PluginInterface):
            @property
            def metadata(self) -> PluginMetadata:
                return PluginMetadata(name="my_plugin", version="1.0.0")
            
            async def on_load(self, config):
                pass
            
            async def on_unload(self):
                pass
        
        plugin = MyPlugin()
        assert plugin.metadata.name == "my_plugin"
