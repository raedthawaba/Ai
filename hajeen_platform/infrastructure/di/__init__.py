"""
Dependency Injection Container
===========================

Provides a robust dependency injection container with:
- Singleton and transient registration
- Constructor injection
- Property injection
- Dependency resolution
- Circular dependency detection
- Lifetime management
"""

from __future__ import annotations

import inspect
from typing import (
    Any, Callable, Dict, Generator, Generic, List, 
    Optional, Type, TypeVar, Union, get_type_hints, get_origin, get_args
)
from dataclasses import dataclass
from enum import Enum
import logging
import threading

logger = logging.getLogger(__name__)

T = TypeVar('T')
TInterface = TypeVar('TInterface')


class Lifetime(Enum):
    """Service lifetime."""
    TRANSIENT = "transient"      # New instance each time
    SCOPED = "scoped"           # One instance per scope
    SINGLETON = "singleton"      # One instance for entire app


class InjectionType(Enum):
    """Dependency injection type."""
    CONSTRUCTOR = "constructor"
    PROPERTY = "property"
    METHOD = "method"


@dataclass
class ServiceDescriptor:
    """Service registration descriptor."""
    service_type: Type
    implementation: Optional[Type] = None
    factory: Optional[Callable] = None
    lifetime: Lifetime = Lifetime.TRANSIENT
    instance: Any = None
    injected_dependencies: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.injected_dependencies is None:
            self.injected_dependencies = {}


class CircularDependencyError(Exception):
    """Raised when circular dependency is detected."""
    pass


class ResolutionError(Exception):
    """Raised when dependency cannot be resolved."""
    pass


class Container:
    """
    Dependency Injection Container.
    
    Usage:
        container = Container()
        
        # Register services
        container.register(Service, Lifetime.SINGLETON)
        container.register(IService, Service)  # Interface to implementation
        
        # Resolve
        service = container.resolve(Service)
        
        # Inject into existing instance
        container.inject_dependencies(instance)
    """
    
    _instance: Optional[Container] = None
    
    def __init__(self, parent: Optional[Container] = None):
        self._services: Dict[str, ServiceDescriptor] = {}
        self._singletons: Dict[str, Any] = {}
        self._parent = parent
        self._lock = threading.RLock()
        self._resolving: set = set()  # Track正在解析的服务，防止循环依赖
    
    @classmethod
    def get_instance(cls) -> Container:
        """Get singleton container instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def set_instance(cls, container: Container):
        """Set singleton container instance."""
        cls._instance = container
    
    def register(
        self,
        service: Union[Type, str],
        lifetime: Lifetime = Lifetime.TRANSIENT,
        implementation: Optional[Type] = None,
        factory: Optional[Callable] = None
    ) -> Container:
        """
        Register a service.
        
        Args:
            service: Service type or name
            lifetime: Service lifetime
            implementation: Concrete implementation type
            factory: Factory function to create service
        """
        with self._lock:
            key = service if isinstance(service, str) else self._get_key(service)
            
            # Check if already registered
            if key in self._services:
                logger.warning(f"Service {key} already registered, overwriting")
            
            self._services[key] = ServiceDescriptor(
                service_type=service if not isinstance(service, str) else None,
                implementation=implementation,
                factory=factory,
                lifetime=lifetime
            )
            
            logger.debug(f"Registered service: {key} ({lifetime.value})")
        
        return self
    
    def register_singleton(
        self,
        service: Type,
        implementation: Optional[Type] = None
    ) -> Container:
        """Register a singleton service."""
        return self.register(service, Lifetime.SINGLETON, implementation)
    
    def register_transient(
        self,
        service: Type,
        implementation: Optional[Type] = None
    ) -> Container:
        """Register a transient service."""
        return self.register(service, Lifetime.TRANSIENT, implementation)
    
    def register_instance(self, service: Type, instance: Any) -> Container:
        """Register an existing instance as singleton."""
        with self._lock:
            key = self._get_key(service)
            self._services[key] = ServiceDescriptor(
                service_type=service,
                lifetime=Lifetime.SINGLETON,
                instance=instance
            )
            self._singletons[key] = instance
        return self
    
    def unregister(self, service: Type) -> bool:
        """Unregister a service."""
        with self._lock:
            key = self._get_key(service)
            if key in self._services:
                del self._services[key]
                self._singletons.pop(key, None)
                return True
            return False
    
    def resolve(self, service: Type[T]) -> T:
        """
        Resolve a service by type.
        
        Args:
            service: Service type to resolve
            
        Returns:
            Resolved service instance
        """
        key = self._get_key(service)
        
        with self._lock:
            # Check if already resolving (circular dependency)
            if key in self._resolving:
                raise CircularDependencyError(
                    f"Circular dependency detected while resolving {key}"
                )
            
            # Check if registered
            if key not in self._services:
                # Try parent container
                if self._parent:
                    return self._parent.resolve(service)
                raise ResolutionError(f"Service not registered: {key}")
            
            descriptor = self._services[key]
            
            # Return existing instance for singleton
            if descriptor.lifetime == Lifetime.SINGLETON:
                if key in self._singletons:
                    return self._singletons[key]
            
            # Mark as resolving
            self._resolving.add(key)
            
            try:
                # Create instance
                instance = self._create_instance(descriptor)
                
                # Store singleton
                if descriptor.lifetime == Lifetime.SINGLETON:
                    self._singletons[key] = instance
                
                return instance
                
            finally:
                self._resolving.discard(key)
    
    def resolve_optional(self, service: Type[T]) -> Optional[T]:
        """Resolve a service, returning None if not registered."""
        try:
            return self.resolve(service)
        except ResolutionError:
            return None
    
    def resolve_all(self, service: Type[T]) -> List[T]:
        """Resolve all services implementing an interface."""
        results = []
        key = self._get_key(service)
        
        for registered_key, descriptor in self._services.items():
            if registered_key == key or (
                descriptor.implementation and 
                issubclass(descriptor.implementation, service)
            ):
                results.append(self.resolve(registered_key))
        
        return results
    
    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """Create an instance from descriptor."""
        # Use existing instance
        if descriptor.instance is not None:
            return descriptor.instance
        
        # Use factory
        if descriptor.factory is not None:
            return descriptor.factory(self)
        
        # Use implementation
        impl_type = descriptor.implementation or descriptor.service_type
        
        if impl_type is None:
            raise ResolutionError("No implementation or factory for service")
        
        # Inject dependencies
        instance = self._inject_dependencies(impl_type)
        
        return instance
    
    def _inject_dependencies(self, impl_type: Type) -> Any:
        """Inject dependencies into a class constructor."""
        # Get constructor
        init_method = getattr(impl_type, '__init__', None)
        if init_method is None:
            return impl_type()
        
        # Get type hints
        try:
            hints = get_type_hints(init_method)
        except Exception:
            hints = {}
        
        # Get parameter names
        try:
            sig = inspect.signature(init_method)
            param_names = list(sig.parameters.keys())
        except (ValueError, TypeError):
            param_names = []
        
        # Resolve dependencies
        kwargs = {}
        for param_name in param_names:
            if param_name == 'self':
                continue
            
            param_type = hints.get(param_name)
            if param_type:
                try:
                    resolved = self.resolve(param_type)
                    kwargs[param_name] = resolved
                except ResolutionError:
                    # Try to get default value
                    pass
        
        # Create instance
        try:
            return impl_type(**kwargs)
        except TypeError as e:
            logger.error(f"Failed to create {impl_type.__name__}: {e}")
            # Fallback: try without type hints
            return impl_type()
    
    def inject_dependencies(self, instance: Any) -> Any:
        """
        Inject dependencies into an existing instance.
        
        Looks for attributes with type hints and injects them.
        """
        hints = get_type_hints(type(instance).__init__)
        
        for attr_name, attr_type in hints.items():
            if attr_name == 'self':
                continue
            
            if hasattr(instance, attr_name):
                continue  # Already set
            
            try:
                resolved = self.resolve(attr_type)
                setattr(instance, attr_name, resolved)
            except ResolutionError:
                pass
        
        return instance
    
    def create_scope(self) -> ScopedContainer:
        """Create a scoped container."""
        return ScopedContainer(self)
    
    def clear(self):
        """Clear all registrations."""
        with self._lock:
            self._services.clear()
            self._singletons.clear()
    
    def _get_key(self, service: Type) -> str:
        """Get registration key for service type."""
        if isinstance(service, str):
            return service
        return f"{service.__module__}.{service.__qualname__}"
    
    def __contains__(self, service: Type) -> bool:
        """Check if service is registered."""
        key = self._get_key(service)
        return key in self._services or (
            self._parent and service in self._parent
        )
    
    def __repr__(self) -> str:
        return f"<Container services={len(self._services)}>"


class ScopedContainer:
    """Scoped container for request/session lifetime."""
    
    def __init__(self, parent: Container):
        self._parent = parent
        self._singletons: Dict[str, Any] = {}
        self._services: Dict[str, ServiceDescriptor] = {}
    
    def register(
        self,
        service: Type,
        lifetime: Lifetime = Lifetime.SCOPED,
        implementation: Optional[Type] = None
    ) -> ScopedContainer:
        """Register a scoped service."""
        key = self._parent._get_key(service)
        self._services[key] = ServiceDescriptor(
            service_type=service,
            implementation=implementation,
            lifetime=lifetime
        )
        return self
    
    def resolve(self, service: Type[T]) -> T:
        """Resolve a scoped service."""
        key = self._parent._get_key(service)
        
        # Check scoped singleton
        if key in self._singletons:
            return self._singletons[key]
        
        # Get descriptor
        descriptor = self._services.get(key) or self._parent._services.get(key)
        if not descriptor:
            raise ResolutionError(f"Service not registered: {key}")
        
        # Create instance
        instance = self._parent._create_instance(descriptor)
        
        # Store scoped singleton
        if descriptor.lifetime in (Lifetime.SINGLETON, Lifetime.SCOPED):
            self._singletons[key] = instance
        
        return instance
    
    def dispose(self):
        """Dispose scoped services."""
        for instance in self._singletons.values():
            if hasattr(instance, 'dispose'):
                try:
                    instance.dispose()
                except Exception as e:
                    logger.error(f"Error disposing {type(instance)}: {e}")
        self._singletons.clear()


# Global container instance
_container: Optional[Container] = None


def get_container() -> Container:
    """Get global container instance."""
    global _container
    if _container is None:
        _container = Container.get_instance()
    return _container


def set_container(container: Container):
    """Set global container instance."""
    global _container
    _container = container
    Container.set_instance(container)


# Decorator for dependency injection
def inject(service: Type, lifetime: Lifetime = Lifetime.TRANSIENT):
    """
    Decorator for automatic dependency injection.
    
    Usage:
        @inject(Service)
        class MyClass:
            def __init__(self, service: Service):
                self.service = service
    """
    def decorator(cls):
        original_init = cls.__init__
        
        def new_init(self, *args, **kwargs):
            container = get_container()
            original_init(self, *args, **kwargs)
            container.inject_dependencies(self)
        
        cls.__init__ = new_init
        return cls
    
    return decorator


# Auto-registration decorator
def injectable(lifetime: Lifetime = Lifetime.TRANSIENT):
    """
    Decorator to mark a class as injectable and auto-register it.
    
    Usage:
        @injectable(Lifetime.SINGLETON)
        class MyService:
            def __init__(self, dep: Dependency):
                self.dep = dep
    """
    def decorator(cls):
        container = get_container()
        container.register(cls, lifetime)
        return cls
    
    return decorator
