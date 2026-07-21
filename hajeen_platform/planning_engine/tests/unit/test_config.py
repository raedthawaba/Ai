"""Unit tests for Configuration Manager."""
import json
import tempfile
from pathlib import Path

import pytest
import yaml

from planning_engine.config.manager import (
    ConfigurationManager,
    ConfigFormat,
    ConfigSchema,
    get_config,
)


class TestConfigurationManager:
    """Tests for ConfigurationManager class."""

    @pytest.fixture
    def config_manager(self):
        """Create config manager instance."""
        return ConfigurationManager()

    def test_add_source_data(self, config_manager):
        """Test adding a data source."""
        config_manager.add_source(
            name="test_source",
            format=ConfigFormat.JSON,
            data={"key": "value"},
            priority=10,
        )
        
        assert len(config_manager._sources) == 1
        assert config_manager._sources[0].name == "test_source"

    def test_load_with_defaults(self, config_manager):
        """Test loading with default values."""
        config = config_manager.load()
        
        assert "engine" in config
        assert "logging" in config
        assert config["engine"]["max_concurrent_steps"] == 10

    def test_load_from_json_file(self, config_manager):
        """Test loading from JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"custom_key": "custom_value", "engine": {"max_concurrent_steps": 20}}, f)
            temp_path = Path(f.name)
        
        try:
            config_manager.add_source(
                name="json_source",
                format=ConfigFormat.JSON,
                path=temp_path,
            )
            config = config_manager.load()
            
            assert config["custom_key"] == "custom_value"
            assert config["engine"]["max_concurrent_steps"] == 20
        finally:
            temp_path.unlink()

    def test_load_from_yaml_file(self, config_manager):
        """Test loading from YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"custom_key": "yaml_value", "engine": {"default_timeout_seconds": 30.0}}, f)
            temp_path = Path(f.name)
        
        try:
            config_manager.add_source(
                name="yaml_source",
                format=ConfigFormat.YAML,
                path=temp_path,
            )
            config = config_manager.load()
            
            assert config["custom_key"] == "yaml_value"
            assert config["engine"]["default_timeout_seconds"] == 30.0
        finally:
            temp_path.unlink()

    def test_get_value(self, config_manager):
        """Test getting config values."""
        config_manager.load()
        
        value = config_manager.get("engine.max_concurrent_steps")
        assert value == 10
        
        value = config_manager.get("nonexistent.key", "default")
        assert value == "default"

    def test_set_value(self, config_manager):
        """Test setting config values."""
        config_manager.load()
        
        config_manager.set("engine.max_concurrent_steps", 50)
        value = config_manager.get("engine.max_concurrent_steps")
        
        assert value == 50

    def test_deep_merge(self, config_manager):
        """Test deep merging of configs."""
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10, "e": 20}, "f": 30}
        
        result = config_manager._deep_merge(base, override)
        
        assert result["a"]["b"] == 10
        assert result["a"]["c"] == 2
        assert result["a"]["e"] == 20
        assert result["d"] == 3
        assert result["f"] == 30

    def test_set_secret(self, config_manager):
        """Test setting secrets."""
        config_manager.load()
        config_manager.set_secret("api_key", "secret123")
        
        assert config_manager._secrets["api_key"] == "secret123"

    def test_validate(self, config_manager):
        """Test config validation."""
        config_manager.load()
        errors = config_manager.validate()
        
        assert isinstance(errors, list)

    def test_export_json(self, config_manager):
        """Test exporting to JSON."""
        config_manager.load()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            config_manager.export(temp_path, ConfigFormat.JSON)
            
            with open(temp_path) as f:
                data = json.load(f)
            
            assert "engine" in data
        finally:
            temp_path.unlink()

    def test_export_yaml(self, config_manager):
        """Test exporting to YAML."""
        config_manager.load()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            config_manager.export(temp_path, ConfigFormat.YAML)
            
            with open(temp_path) as f:
                data = yaml.safe_load(f)
            
            assert "engine" in data
        finally:
            temp_path.unlink()

    def test_listener(self, config_manager):
        """Test config change listeners."""
        config_manager.load()
        
        changes = []
        def listener(key, value):
            changes.append((key, value))
        
        config_manager.add_listener(listener)
        config_manager.set("test.key", "test_value")
        
        assert len(changes) == 1
        assert changes[0] == ("test.key", "test_value")

    def test_remove_listener(self, config_manager):
        """Test removing listeners."""
        config_manager.load()
        
        def listener(key, value):
            pass
        
        config_manager.add_listener(listener)
        config_manager.remove_listener(listener)
        
        assert listener not in config_manager._listeners

    def test_singleton(self):
        """Test singleton pattern."""
        # Reset singleton
        import planning_engine.config.manager as config_module
        config_module._config_manager = None
        
        manager1 = get_config()
        manager2 = get_config()
        
        assert manager1 is manager2
