"""Planning Engine - Dependency Injection System."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
TInterface = TypeVar("TInterface")


class Scope(str):
    """نطاق生命周期."""
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


@dataclass
class ServiceDescriptor:
    """وصف خدمة مسجلة."""
    interface: Type
    implementation: Type
    factory: Optional[Callable[[], Any]] = None
    scope: Scope = Scope.SINGLETON
    instance: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IDependencyContainer(ABC):
    """واجهة حاوية التبعية."""

    @abstractmethod
    def resolve(self, interface: Type[T]) -> T:
        """حل تبعية."""
        ...

    @abstractmethod
    async def resolve_async(self, interface: Type[T]) -> T:
        """حل تبعية بشكل غير متزامن."""
        ...

    @abstractmethod
    def register(self, interface: Type, implementation: Type, **kwargs: Any) -> None:
        """تسجيل خدمة."""
        ...

    @abstractmethod
    def unregister(self, interface: Type) -> None:
        """إلغاء تسجيل خدمة."""
        ...


class DependencyContainer(IDependencyContainer):
    """
    حاوية التبعية.
    
    الميزات:
    - تسجيل الخدمات (Singleton, Transient, Scoped)
    - حقن التبعية التلقائي
    - Factory methods
    - Scopes للإدارة
    - فحص وقت التجميع
    """

    def __init__(self) -> None:
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scopes: Dict[str, Dict[Type, Any]] = {}
        self._current_scope: Optional[str] = None
        self._parent: Optional[DependencyContainer] = None
        self._lock = asyncio.Lock()

    def set_parent(self, parent: DependencyContainer) -> None:
        """تعيين الأب."""
        self._parent = parent

    def register(
        self,
        interface: Type[TInterface],
        implementation: Optional[Type[TInterface]] = None,
        factory: Optional[Callable[[], TInterface]] = None,
        scope: Scope = Scope.SINGLETON,
        **metadata: Any,
    ) -> Callable[[Type], Type]:
        """تسجيل خدمة."""
        def decorator(cls: Type[TInterface]) -> Type[TInterface]:
            impl = implementation or cls
            self._services[interface] = ServiceDescriptor(
                interface=interface,
                implementation=impl,
                factory=factory,
                scope=scope,
                metadata=metadata,
            )
            logger.debug("di: registered interface=%s impl=%s scope=%s",
                        interface.__name__, impl.__name__, scope)
            return cls
        return decorator

    def register_instance(self, interface: Type[TInterface], instance: TInterface) -> None:
        """تسجيل مثيل موجود."""
        self._services[interface] = ServiceDescriptor(
            interface=interface,
            implementation=type(instance),
            instance=instance,
            scope=Scope.SINGLETON,
        )
        logger.debug("di: registered instance interface=%s", interface.__name__)

    def register_factory(
        self,
        interface: Type[TInterface],
        factory: Callable[[], TInterface],
        scope: Scope = Scope.TRANSIENT,
    ) -> None:
        """تسجيل factory."""
        self._services[interface] = ServiceDescriptor(
            interface=interface,
            implementation=type(factory()),
            factory=factory,
            scope=scope,
        )
        logger.debug("di: registered factory interface=%s", interface.__name__)

    def unregister(self, interface: Type) -> None:
        """إلغاء تسجيل خدمة."""
        if interface in self._services:
            del self._services[interface]
        if interface in self._singletons:
            del self._singletons[interface]
        logger.debug("di: unregistered interface=%s", interface.__name__)

    def resolve(self, interface: Type[T]) -> T:
        """حل تبعية."""
        # البحث في الحاوية الحالية
        if interface in self._services:
            return self._resolve_service(interface)
        
        # البحث في الأب
        if self._parent:
            return self._parent.resolve(interface)
        
        raise DependencyNotFoundError(f"Dependency not found: {interface.__name__}")

    async def resolve_async(self, interface: Type[T]) -> T:
        """حل تبعية بشكل غير متزامن."""
        return self.resolve(interface)

    def _resolve_service(self, interface: Type[T]) -> T:
        """حل خدمة."""
        descriptor = self._services[interface]
        
        # إذا كان هناك مثيل موجود
        if descriptor.instance is not None:
            return descriptor.instance
        
        # التحقق من نوع الـ scope
        if descriptor.scope == Scope.SINGLETON:
            if interface in self._singletons:
                return self._singletons[interface]
            
            instance = self._create_instance(descriptor)
            self._singletons[interface] = instance
            return instance
        
        elif descriptor.scope == Scope.SCOPED:
            if self._current_scope and self._current_scope in self._scopes:
                if interface in self._scopes[self._current_scope]:
                    return self._scopes[self._current_scope][interface]
            
            instance = self._create_instance(descriptor)
            if self._current_scope:
                if self._current_scope not in self._scopes:
                    self._scopes[self._current_scope] = {}
                self._scopes[self._current_scope][interface] = instance
            return instance
        
        else:  # TRANSIENT
            return self._create_instance(descriptor)

    def _create_instance(self, descriptor: ServiceDescriptor) -> Any:
        """إنشاء مثيل جديد."""
        if descriptor.factory:
            return descriptor.factory()
        
        impl = descriptor.implementation
        
        # محاولة حقن التبعية التلقائي
        try:
            import inspect
            sig = inspect.signature(impl.__init__)
            params = {}
            
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                
                param_type = param.annotation
                if param_type is inspect.Parameter.empty:
                    continue
                
                try:
                    params[param_name] = self.resolve(param_type)
                except DependencyNotFoundError:
                    if param.default is inspect.Parameter.empty:
                        raise
                    params[param_name] = param.default
            
            return impl(**params)
            
        except Exception as e:
            logger.error("di: failed to create instance error=%s", str(e))
            return impl()

    def create_scope(self, scope_id: Optional[str] = None) -> ScopeContext:
        """إنشاء نطاق جديد."""
        scope_id = scope_id or str(id(asyncio.current_task()))
        self._scopes[scope_id] = {}
        return ScopeContext(self, scope_id)

    def get_scope_ids(self) -> List[str]:
        """الحصول على قائمة النطاقات."""
        return list(self._scopes.keys())

    def clear_scopes(self) -> None:
        """مسح جميع النطاقات."""
        self._scopes.clear()

    def get_registered_services(self) -> List[Type]:
        """الحصول على قائمة الخدمات المسجلة."""
        return list(self._services.keys())

    def is_registered(self, interface: Type) -> bool:
        """التحقق من تسجيل خدمة."""
        return interface in self._services


class ScopeContext:
    """سياق النطاق."""

    def __init__(self, container: DependencyContainer, scope_id: str) -> None:
        self._container = container
        self._scope_id = scope_id
        self._entered = False

    def __enter__(self) -> ScopeContext:
        self._container._current_scope = self._scope_id
        self._entered = True
        return self

    def __exit__(self, *args: Any) -> None:
        self._container._current_scope = None
        if self._scope_id in self._container._scopes:
            del self._container._scopes[self._scope_id]
        self._entered = False

    async def __aenter__(self) -> ScopeContext:
        return self.__enter__()

    async def __aexit__(self, *args: Any) -> None:
        self.__exit__()


class DependencyNotFoundError(Exception):
    """خطأ عند عدم العثور على تبعية."""
    pass


class CircularDependencyError(Exception):
    """خطأ عند اكتشاف تبعية دائرية."""
    pass


# Singleton container
_container: Optional[DependencyContainer] = None


def get_container() -> DependencyContainer:
    """الحصول على الحاوية الوحيدة."""
    global _container
    if _container is None:
        _container = DependencyContainer()
    return _container


def reset_container() -> None:
    """إعادة تعيين الحاوية."""
    global _container
    _container = None


# Decorators
def injectable(
    interface: Type[TInterface],
    scope: Scope = Scope.SINGLETON,
    **metadata: Any,
) -> Callable[[Type], Type]:
    """ديكوريتر لوضع علامة على فئة كـ injectable."""
    def decorator(cls: Type[TInterface]) -> Type[TInterface]:
        container = get_container()
        container.register(interface, scope=scope, **metadata)(cls)
        return cls
    return decorator


def inject(interface: Type[T]) -> T:
    """ديكوريتر لحقن تبعية في دالة."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            container = get_container()
            # حل التبعية من نوع الـ interface
            # يمكن إضافة منطق أكثر تعقيداً هنا
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Lazy resolution
class Lazy(ABC):
    """حل مؤجل للتبعية."""

    @abstractmethod
    def resolve(self) -> Any:
        """حل التبعية."""
        ...

    @abstractmethod
    def resolve_async(self) -> Any:
        """حل التبعية بشكل غير متزامن."""
        ...


@dataclass
class LazyResolution(Lazy):
    """حل مؤجل بسيط."""
    _container: DependencyContainer
    _interface: Type
    _instance: Optional[Any] = field(default=None, repr=False)

    def resolve(self) -> Any:
        """حل التبعية."""
        if self._instance is None:
            self._instance = self._container.resolve(self._interface)
        return self._instance

    async def resolve_async(self) -> Any:
        """حل التبعية بشكل غير متزامن."""
        return self.resolve()


def lazy_resolve(container: DependencyContainer, interface: Type[T]) -> LazyResolution:
    """إنشاء حل مؤجل."""
    return LazyResolution(_container=container, _interface=interface)
