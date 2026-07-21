"""Planning Engine - Registry Pattern Implementation."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
TService = TypeVar("TService")


class RegistryScope(str, Enum):
    """نطاق السجل."""
    GLOBAL = "global"
    LOCAL = "local"
    SESSION = "session"


@dataclass
class ServiceRegistration:
    """تسجيل خدمة."""
    service_id: str
    service_type: Type
    implementation: Type
    instance: Optional[Any] = None
    factory: Optional[Callable[[], Any]] = None
    scope: RegistryScope = RegistryScope.GLOBAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: Optional[datetime] = None
    access_count: int = 0


@dataclass
class ServiceHealth:
    """صحة الخدمة."""
    service_id: str
    is_healthy: bool
    last_check: datetime
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IServiceRegistry(ABC):
    """واجهة سجل الخدمات."""

    @abstractmethod
    def register(
        self,
        service_id: str,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        **metadata: Any,
    ) -> None:
        """تسجيل خدمة."""
        ...

    @abstractmethod
    def unregister(self, service_id: str) -> bool:
        """إلغاء تسجيل خدمة."""
        ...

    @abstractmethod
    def resolve(self, service_id: str) -> Any:
        """حل خدمة."""
        ...

    @abstractmethod
    def list_services(self) -> List[str]:
        """قائمة الخدمات."""
        ...

    @abstractmethod
    def get_metadata(self, service_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على بيانات الخدمة."""
        ...


class ServiceRegistry(IServiceRegistry):
    """
    سجل الخدمات الأساسي.
    
    الميزات:
    - تسجيل/إلغاء تسجيل الخدمات
    - حل الخدمات (Resolution)
    - Factory methods
    - Scopes (Global, Local, Session)
    - Health checks
    - Discovery
    """

    def __init__(self, scope: RegistryScope = RegistryScope.GLOBAL) -> None:
        self._scope = scope
        self._services: Dict[str, ServiceRegistration] = {}
        self._aliases: Dict[str, str] = {}
        self._health_checks: Dict[str, Callable[[], bool]] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        service_id: str,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        factory: Optional[Callable[[], T]] = None,
        scope: Optional[RegistryScope] = None,
        **metadata: Any,
    ) -> None:
        """تسجيل خدمة."""
        if service_id in self._services:
            logger.warning("registry: service already registered %s", service_id)
            return
        
        registration = ServiceRegistration(
            service_id=service_id,
            service_type=service_type,
            implementation=implementation or service_type,
            factory=factory,
            scope=scope or self._scope,
            metadata=metadata,
        )
        
        self._services[service_id] = registration
        logger.debug("registry: registered service_id=%s type=%s", 
                    service_id, service_type.__name__)

    def unregister(self, service_id: str) -> bool:
        """إلغاء تسجيل خدمة."""
        if service_id in self._services:
            del self._services[service_id]
            # إزالة الـ aliases
            aliases_to_remove = [k for k, v in self._aliases.items() if v == service_id]
            for alias in aliases_to_remove:
                del self._aliases[alias]
            logger.debug("registry: unregistered service_id=%s", service_id)
            return True
        return False

    def register_factory(
        self,
        service_id: str,
        factory: Callable[[], T],
        service_type: Optional[Type[T]] = None,
        scope: Optional[RegistryScope] = None,
        **metadata: Any,
    ) -> None:
        """تسجيل factory method."""
        if service_id in self._services:
            logger.warning("registry: service already registered %s", service_id)
            return
        
        # Create a temporary instance to get the type if not provided
        temp_instance = factory()
        impl_type = service_type or type(temp_instance)
        
        registration = ServiceRegistration(
            service_id=service_id,
            service_type=impl_type,
            implementation=impl_type,
            factory=factory,
            scope=scope or self._scope,
            metadata=metadata,
        )
        
        self._services[service_id] = registration
        logger.debug("registry: registered factory service_id=%s", service_id)

    def resolve(self, service_id: str) -> Any:
        """حل خدمة."""
        registration = self._services.get(service_id)
        if not registration:
            raise ServiceNotFoundError(f"Service not found: {service_id}")
        
        # تحديث آخر وصول
        registration.last_accessed = datetime.utcnow()
        registration.access_count += 1
        
        # إنشاء المثيل إذا لزم
        if registration.instance is None:
            if registration.factory:
                registration.instance = registration.factory()
            else:
                registration.instance = registration.implementation()
        
        return registration.instance

    def resolve_or_none(self, service_id: str) -> Optional[Any]:
        """حل خدمة مع إرجاع None إذا لم توجد."""
        try:
            return self.resolve(service_id)
        except ServiceNotFoundError:
            return None

    def register_alias(self, alias: str, service_id: str) -> None:
        """تسجيل اسم مستعار لخدمة."""
        if service_id not in self._services:
            raise ServiceNotFoundError(f"Service not found: {service_id}")
        self._aliases[alias] = service_id
        logger.debug("registry: aliased %s -> %s", alias, service_id)

    def resolve_by_alias(self, alias: str) -> Any:
        """حل خدمة بالاسم المستعار."""
        service_id = self._aliases.get(alias)
        if not service_id:
            raise ServiceNotFoundError(f"Alias not found: {alias}")
        return self.resolve(service_id)

    def create_instance(
        self,
        service_id: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """إنشاء مثيل جديد من خدمة."""
        registration = self._services.get(service_id)
        if not registration:
            raise ServiceNotFoundError(f"Service not found: {service_id}")
        
        impl = registration.implementation
        
        # محاولة حقن التبعية
        import inspect
        sig = inspect.signature(impl.__init__)
        params = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            
            if param_name in kwargs:
                params[param_name] = kwargs[param_name]
            elif param.annotation is not inspect.Parameter.empty:
                try:
                    params[param_name] = self.resolve(param.annotation.__name__)
                except ServiceNotFoundError:
                    if param.default is inspect.Parameter.empty:
                        raise
        
        return impl(*args, **params)

    def register_health_check(
        self,
        service_id: str,
        health_check: Callable[[], bool],
    ) -> None:
        """تسجيل فحص صحة لخدمة."""
        self._health_checks[service_id] = health_check
        logger.debug("registry: registered health check for %s", service_id)

    async def check_health(self, service_id: str) -> ServiceHealth:
        """فحص صحة خدمة."""
        registration = self._services.get(service_id)
        if not registration:
            raise ServiceNotFoundError(f"Service not found: {service_id}")
        
        health_check = self._health_checks.get(service_id)
        
        if health_check:
            import time
            start = time.time()
            try:
                is_healthy = health_check()
                response_time = (time.time() - start) * 1000
                return ServiceHealth(
                    service_id=service_id,
                    is_healthy=is_healthy,
                    last_check=datetime.utcnow(),
                    response_time_ms=response_time,
                )
            except Exception as e:
                return ServiceHealth(
                    service_id=service_id,
                    is_healthy=False,
                    last_check=datetime.utcnow(),
                    error_message=str(e),
                )
        
        return ServiceHealth(
            service_id=service_id,
            is_healthy=True,
            last_check=datetime.utcnow(),
        )

    async def check_all_health(self) -> Dict[str, ServiceHealth]:
        """فحص صحة جميع الخدمات."""
        results = {}
        for service_id in self._services:
            try:
                results[service_id] = await self.check_health(service_id)
            except Exception as e:
                results[service_id] = ServiceHealth(
                    service_id=service_id,
                    is_healthy=False,
                    last_check=datetime.utcnow(),
                    error_message=str(e),
                )
        return results

    def list_services(self) -> List[str]:
        """قائمة الخدمات المسجلة."""
        return list(self._services.keys())

    def list_by_type(self, service_type: Type) -> List[str]:
        """قائمة الخدمات من نوع معين."""
        return [
            sid for sid, reg in self._services.items()
            if reg.service_type == service_type or reg.implementation == service_type
        ]

    def get_metadata(self, service_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على بيانات الخدمة."""
        registration = self._services.get(service_id)
        return registration.metadata if registration else None

    def get_registration(self, service_id: str) -> Optional[ServiceRegistration]:
        """الحصول على تسجيل الخدمة."""
        return self._services.get(service_id)

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات."""
        total_accesses = sum(r.access_count for r in self._services.values())
        
        return {
            "total_services": len(self._services),
            "total_aliases": len(self._aliases),
            "total_accesses": total_accesses,
            "services": {
                sid: {
                    "type": reg.service_type.__name__,
                    "scope": reg.scope.value,
                    "access_count": reg.access_count,
                    "has_instance": reg.instance is not None,
                }
                for sid, reg in self._services.items()
            },
        }

    def clear(self) -> None:
        """مسح جميع الخدمات."""
        self._services.clear()
        self._aliases.clear()
        logger.info("registry: cleared")


class ServiceNotFoundError(Exception):
    """خطأ عند عدم العثور على الخدمة."""
    pass


class ServiceAlreadyRegisteredError(Exception):
    """خطأ عند تسجيل خدمة موجودة."""
    pass


# Registry with versioning
@dataclass
class VersionedServiceRegistration(ServiceRegistration):
    """تسجيل خدمة مع إصدارات."""
    version: str = "1.0.0"
    previous_version: Optional[str] = None


class VersionedServiceRegistry(ServiceRegistry):
    """سجل الخدمات مع دعم الإصدارات."""

    def __init__(self) -> None:
        super().__init__()
        self._versioned_services: Dict[str, Dict[str, VersionedServiceRegistration]] = {}

    def register_versioned(
        self,
        service_id: str,
        version: str,
        service_type: Type[T],
        implementation: Optional[Type[T]] = None,
        **metadata: Any,
    ) -> None:
        """تسجيل خدمة محددة الإصدار."""
        if service_id not in self._versioned_services:
            self._versioned_services[service_id] = {}
        
        registration = VersionedServiceRegistration(
            service_id=service_id,
            service_type=service_type,
            implementation=implementation or service_type,
            version=version,
            metadata=metadata,
        )
        
        # تحديد الإصدار السابق
        if service_id in self._services:
            old_reg = self._services[service_id]
            if isinstance(old_reg, VersionedServiceRegistration):
                registration.previous_version = old_reg.version
        
        self._versioned_services[service_id][version] = registration
        self._services[service_id] = registration
        
        logger.info("registry: registered versioned service %s v%s", service_id, version)

    def resolve_version(self, service_id: str, version: str) -> Any:
        """حل خدمة بإصدار محدد."""
        if service_id not in self._versioned_services:
            raise ServiceNotFoundError(f"Service not found: {service_id}")
        
        if version not in self._versioned_services[service_id]:
            raise ServiceNotFoundError(f"Version {version} not found for {service_id}")
        
        return self.resolve(service_id)

    def get_versions(self, service_id: str) -> List[str]:
        """الحصول على قائمة إصدارات الخدمة."""
        if service_id not in self._versioned_services:
            return []
        return sorted(self._versioned_services[service_id].keys())

    def get_latest_version(self, service_id: str) -> Optional[str]:
        """الحصول على آخر إصدار."""
        versions = self.get_versions(service_id)
        return versions[-1] if versions else None


# Discovery service
class ServiceDiscovery:
    """اكتشاف الخدمات."""

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self._discoverers: Dict[str, Callable[[str], List[str]]] = {}

    def register_discoverer(
        self,
        namespace: str,
        discoverer: Callable[[str], List[str]],
    ) -> None:
        """تسجيل discoverer."""
        self._discoverers[namespace] = discoverer

    def discover(self, namespace: str, pattern: str = "*") -> List[str]:
        """اكتشاف الخدمات."""
        if namespace in self._discoverers:
            return self._discoverers[namespace](pattern)
        
        # اكتشاف من السجل
        services = self._registry.list_services()
        if pattern == "*":
            return services
        
        import fnmatch
        return [s for s in services if fnmatch.fnmatch(s, pattern)]

    def discover_by_metadata(
        self,
        key: str,
        value: Any,
    ) -> List[str]:
        """اكتشاف الخدمات بالبيانات."""
        results = []
        for service_id in self._registry.list_services():
            metadata = self._registry.get_metadata(service_id)
            if metadata and metadata.get(key) == value:
                results.append(service_id)
        return results


# Singleton instances
_registry: Optional[ServiceRegistry] = None
_versioned_registry: Optional[VersionedServiceRegistry] = None


def get_registry() -> ServiceRegistry:
    """الحصول على سجل الخدمات الوحيد."""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry


def get_versioned_registry() -> VersionedServiceRegistry:
    """الحصول على سجل الخدمات متعدد الإصدارات."""
    global _versioned_registry
    if _versioned_registry is None:
        _versioned_registry = VersionedServiceRegistry()
    return _versioned_registry


# Decorators
def registered_service(
    service_id: str,
    scope: RegistryScope = RegistryScope.GLOBAL,
    **metadata: Any,
) -> Callable[[Type[T]], Type[T]]:
    """ديكوريتر لتسجيل خدمة."""
    def decorator(cls: Type[T]) -> Type[T]:
        registry = get_registry()
        registry.register(
            service_id=service_id,
            service_type=cls,
            scope=scope,
            **metadata,
        )
        return cls
    return decorator


def injectable_service(
    service_id: str,
) -> Callable[[Type[T]], Type[T]]:
    """ديكوريتر لوضع علامة على خدمة قابلة للحقن."""
    def decorator(cls: Type[T]) -> Type[T]:
        cls._service_id = service_id
        return cls
    return decorator
