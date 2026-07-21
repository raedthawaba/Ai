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


class DummyServiceWithDep:
    """Service with dependency."""
    def __init__(self, dummy: DummyService):
        self.dummy = dummy


class TestDependencyContainer:
    """Tests for DependencyContainer class."""

    @pytest.fixture
    def container(self):
        """Create container instance."""
        return DependencyContainer()

    def test_register_class(self, container):
        """Test registering a class."""
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        
        assert DummyService in container._services

    def test_register_instance(self, container):
        """Test registering an instance."""
        instance = DummyService("custom")
        container.register_instance(DummyService, instance)
        
        resolved = container.resolve(DummyService)
        assert resolved.value == "custom"
        assert resolved is instance

    def test_register_decorator(self, container):
        """Test register decorator."""
        @container.register(DummyService, scope=Scope.TRANSIENT)
        class MyService:
            pass
        
        # Note: decorator registers with interface=DummyService
        assert DummyService in container._services

    def test_resolve_singleton(self, container):
        """Test resolving singleton."""
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        
        assert instance1 is instance2

    def test_resolve_transient(self, container):
        """Test resolving transient."""
        container.register(DummyService, DummyService, scope=Scope.TRANSIENT)
        
        instance1 = container.resolve(DummyService)
        instance2 = container.resolve(DummyService)
        
        assert instance1 is not instance2

    def test_resolve_not_found(self, container):
        """Test resolving non-existent service."""
        with pytest.raises(DependencyNotFoundError):
            container.resolve(DummyService)

    def test_resolve_with_default(self, container):
        """Test resolving with default."""
        try:
            result = container.resolve(DummyService)
        except DependencyNotFoundError:
            result = None
        assert result is None

    def test_unregister(self, container):
        """Test unregistering a service."""
        container.register(DummyService, DummyService, scope=Scope.SINGLETON)
        container.unregister(DummyService)
        
        assert DummyService not in container._services

    def test_scope_context(self, container):
        """Test scoped resolution."""
        container.register(DummyService, DummyService, scope=Scope.SCOPED)
        
        with container.create_scope("test_scope") as scope:
            instance1 = container.resolve(DummyService)
        
        with container.create_scope("test_scope2") as scope:
            instance2 = container.resolve(DummyService)
        
        assert instance1 is not instance2

    def test_is_registered(self, container):
        """Test checking registration."""
        assert container.is_registered(DummyService) is False
        
        container.register(DummyService, DummyService)
        assert container.is_registered(DummyService) is True

    def test_get_registered_services(self, container):
        """Test getting registered services."""
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
        container.register(DummyService, scope=Scope.SINGLETON)
        
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
