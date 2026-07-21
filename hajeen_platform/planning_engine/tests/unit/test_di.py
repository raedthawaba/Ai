"""Unit tests for Dependency Injection Container."""
import pytest

from planning_engine.di.container import (
    DependencyContainer,
    Scope,
    ScopeContext,
    DependencyNotFoundError,
    get_container,
    reset_container,
)


class DummyService:
    """Dummy service for testing."""
    def __init__(self, value: str = "default"):
        self.value = value


class AnotherService:
    """Another service for testing."""
    pass


class TestDependencyContainer:
    """Tests for DependencyContainer class."""

    def test_register_class(self):
        """Test registering a class."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        
        assert DummyService in container._services

    def test_register_instance(self):
        """Test registering an instance."""
        container = DependencyContainer()
        instance = DummyService("custom")
        container.register_instance(DummyService, instance)
        
        resolved = container.resolve(DummyService)
        assert resolved.value == "custom"
        assert resolved is instance

    def test_register_decorator(self):
        """Test register decorator."""
        container = DependencyContainer()
        
        @container.register(AnotherService, scope=Scope.TRANSIENT)
        class MyService:
            pass
        
        assert AnotherService in container._services

    def test_resolve_singleton(self):
        """Test resolving singleton."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        
        assert instance1 is instance2

    def test_resolve_transient(self):
        """Test resolving transient."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.TRANSIENT)
        
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        
        assert instance1 is not instance2

    def test_resolve_not_found(self):
        """Test resolving non-existent service."""
        container = DependencyContainer()
        with pytest.raises(DependencyNotFoundError):
            container.resolve(DummyService)

    def test_unregister(self):
        """Test unregistering a service."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        container.unregister(DummyService)
        
        assert DummyService not in container._services

    def test_scope_context(self):
        """Test scoped resolution."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.SCOPED)
        
        with container.create_scope("unique_scope_1") as scope:
            instance1 = container.resolve(DummyService)
        
        with container.create_scope("unique_scope_2") as scope:
            instance2 = container.resolve(DummyService)
        
        assert instance1 is not instance2

    def test_is_registered(self):
        """Test checking registration."""
        container = DependencyContainer()
        assert container.is_registered(DummyService) is False
        
        container.register(DummyService, DummyService)
        assert container.is_registered(DummyService) is True

    def test_get_registered_services(self):
        """Test getting registered services."""
        container = DependencyContainer()
        container.register(DummyService, DummyService)
        
        services = container.get_registered_services()
        assert DummyService in services

    def test_singleton_pattern(self):
        """Test singleton container."""
        reset_container()
        
        container1 = get_container()
        container2 = get_container()
        
        assert container1 is container2


class TestLazyResolution:
    """Tests for lazy resolution."""

    def test_lazy_resolution(self):
        """Test lazy resolution."""
        container = DependencyContainer()
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        
        from planning_engine.di.container import lazy_resolve
        
        lazy = lazy_resolve(container, DummyService)
        
        # Not resolved yet
        assert lazy._instance is None
        
        # Resolve
        instance = lazy.resolve()
        assert instance is not None
        assert isinstance(instance, DummyService)
        
        # Second resolve should return same instance
        instance2 = lazy.resolve()
        assert instance is instance2
