"""Unit tests for Service Registry."""
import pytest

from planning_engine.registry.service import (
    ServiceRegistry,
    RegistryScope,
    ServiceRegistration,
    ServiceNotFoundError,
    get_registry,
    registered_service,
)


class DummyService:
    """Dummy service for registry testing."""
    pass


class AnotherService:
    """Another service type."""
    pass


class TestServiceRegistry:
    """Tests for ServiceRegistry class."""

    @pytest.fixture
    def registry(self):
        """Create registry instance."""
        return ServiceRegistry()

    def test_register_service(self, registry):
        """Test registering a service."""
        registry.register(
            "dummy_service",
            DummyService,
            scope=RegistryScope.GLOBAL,
        )
        
        assert "dummy_service" in registry._services

    def test_unregister_service(self, registry):
        """Test unregistering a service."""
        registry.register("dummy_service", DummyService)
        result = registry.unregister("dummy_service")
        
        assert result is True
        assert "dummy_service" not in registry._services

    def test_resolve_service(self, registry):
        """Test resolving a service."""
        registry.register("dummy_service", DummyService)
        
        instance = registry.resolve("dummy_service")
        
        assert isinstance(instance, DummyService)

    def test_resolve_not_found(self, registry):
        """Test resolving non-existent service."""
        with pytest.raises(ServiceNotFoundError):
            registry.resolve("nonexistent")

    def test_resolve_or_none(self, registry):
        """Test resolve or none."""
        result = registry.resolve_or_none("nonexistent")
        assert result is None

    def test_alias_registration(self, registry):
        """Test registering aliases."""
        registry.register("original", DummyService)
        registry.register_alias("alias", "original")
        
        instance = registry.resolve_by_alias("alias")
        assert isinstance(instance, DummyService)

    def test_health_check(self, registry):
        """Test health check registration."""
        def health_check():
            return True
        
        registry.register("dummy_service", DummyService)
        registry.register_health_check("dummy_service", health_check)

    @pytest.mark.asyncio
    async def test_check_health(self, registry):
        """Test checking service health."""
        def health_check():
            return True
        
        registry.register("dummy_service", DummyService)
        registry.register_health_check("dummy_service", health_check)
        
        health = await registry.check_health("dummy_service")
        
        assert health.is_healthy is True

    def test_list_services(self, registry):
        """Test listing services."""
        registry.register("service1", DummyService)
        registry.register("service2", AnotherService)
        
        services = registry.list_services()
        
        assert len(services) == 2
        assert "service1" in services
        assert "service2" in services

    def test_list_by_type(self, registry):
        """Test listing services by type."""
        registry.register("dummy", DummyService)
        registry.register("another", AnotherService)
        
        services = registry.list_by_type(DummyService)
        
        assert len(services) == 1
        assert "dummy" in services

    def test_get_metadata(self, registry):
        """Test getting service metadata."""
        registry.register(
            "dummy_service",
            DummyService,
            custom_key="custom_value",
        )
        
        metadata = registry.get_metadata("dummy_service")
        
        assert metadata is not None
        assert metadata["custom_key"] == "custom_value"

    def test_statistics(self, registry):
        """Test getting registry statistics."""
        registry.register("service1", DummyService)
        registry.register("service2", AnotherService)
        
        stats = registry.get_statistics()
        
        assert stats["total_services"] == 2
        assert len(stats["services"]) == 2

    def test_clear(self, registry):
        """Test clearing registry."""
        registry.register("service1", DummyService)
        registry.register("service2", AnotherService)
        
        registry.clear()
        
        assert len(registry._services) == 0

    def test_factory_registration(self, registry):
        """Test registering with factory."""
        def factory():
            return DummyService()
        
        registry.register_factory("factory_service", factory, Scope=RegistryScope.TRANSIENT)
        
        instance1 = registry.resolve("factory_service")
        instance2 = registry.resolve("factory_service")
        
        assert isinstance(instance1, DummyService)
        assert instance1 is not instance2

    def test_singleton_pattern(self):
        """Test singleton registry."""
        from planning_engine.registry.service import _registry
        
        # Get and use
        registry = get_registry()
        registry.register("singleton_test", DummyService)
        
        # It should be the same instance
        assert len(registry._services) > 0


class TestDecorators:
    """Tests for registry decorators."""

    def test_registered_service_decorator(self):
        """Test registered_service decorator."""
        @registered_service("decorated_service", scope=RegistryScope.GLOBAL)
        class DecoratedClass:
            pass
        
        # Service should be registered
        registry = get_registry()
        assert "decorated_service" in registry._services
