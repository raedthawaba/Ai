"""
Planning Engine - Hajeen Platform
==================================

محرك التخطيط المتكامل للذكاء الاصطناعي.

المكونات:
- Core: محرك التخطيط الأساسي
- Configuration: نظام الإعدادات
- Pipeline: خط أنابيب التنفيذ
- Execution: تتبع التنفيذ
- Logging: التسجيل المنظم
- Metrics: المقاييس
- Error Recovery: استرداد الأخطاء
- DI: حقن التبعية
- Plugins: نظام الإضافات
- Registry: سجل الخدمات
"""

__version__ = "1.0.0"
__author__ = "Hajeen Team"

# Core
from .core.types import (
    Plan,
    PlanStatus,
    PlanPriority,
    PlanContext,
    ExecutionStep,
    ExecutionState,
    ExecutionResult,
)

from .core.engine import (
    PlanningEngine,
    EngineConfig,
    StepHandler,
    get_engine,
    shutdown_engine,
)

# Configuration
from .config.manager import (
    ConfigurationManager,
    ConfigSchema,
    ConfigFormat,
    get_config,
)

# Pipeline
from .pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineStage,
    PipelineState,
    PipelineContext,
    StageResult,
    StageType,
    PipelineFactory,
)

# Execution
from .execution.trace import (
    ExecutionTrace,
    ExecutionTraceManager,
    TraceEvent,
    TraceEventType,
    TraceLevel,
    get_trace_manager,
)

# Logging
from .structured_logging.logger import (
    configure_logging,
    get_logger,
    get_audit_logger,
    get_audit_logger_singleton,
    LogContext,
    PerformanceLogger,
    RequestLogger,
    set_correlation_id,
    set_plan_id,
    set_pipeline_id,
    get_correlation_id,
    get_plan_id,
    get_pipeline_id,
)

# Metrics
from .metrics.collector import (
    MetricsCollector,
    MetricType,
    Metric,
    BusinessMetrics,
    PerformanceMetrics,
    get_metrics_collector,
)

# Error Recovery
from .error_recovery.recovery import (
    ErrorRecoveryManager,
    RecoveryPolicy,
    ErrorContext,
    RecoveryResult,
    RecoveryAction,
    ErrorSeverity,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    get_error_recovery_manager,
)

# DI
from .di.container import (
    DependencyContainer,
    Scope,
    ScopeContext,
    IDependencyContainer,
    DependencyNotFoundError,
    CircularDependencyError,
    Lazy,
    LazyResolution,
    get_container,
    reset_container,
    injectable,
    inject,
)

# Plugins
from .plugins.manager import (
    PluginManager,
    Plugin,
    PluginState,
    PluginHook,
    PluginMetadata,
    PluginInterface,
    get_plugin_manager,
    plugin,
)

# Registry
from .registry.service import (
    ServiceRegistry,
    VersionedServiceRegistry,
    ServiceRegistry as Registry,
    RegistryScope,
    ServiceRegistration,
    ServiceHealth,
    ServiceDiscovery,
    ServiceNotFoundError,
    ServiceAlreadyRegisteredError,
    get_registry,
    get_versioned_registry,
    registered_service,
    injectable_service,
)

__all__ = [
    # Version
    "__version__",
    
    # Core
    "PlanningEngine",
    "EngineConfig",
    "StepHandler",
    "Plan",
    "PlanStatus",
    "PlanPriority",
    "PlanContext",
    "ExecutionStep",
    "ExecutionState",
    "ExecutionResult",
    "get_engine",
    "shutdown_engine",
    
    # Configuration
    "ConfigurationManager",
    "ConfigSchema",
    "ConfigFormat",
    "get_config",
    
    # Pipeline
    "PipelineOrchestrator",
    "PipelineStage",
    "PipelineState",
    "PipelineContext",
    "StageResult",
    "StageType",
    "PipelineFactory",
    
    # Execution
    "ExecutionTrace",
    "ExecutionTraceManager",
    "TraceEvent",
    "TraceEventType",
    "TraceLevel",
    "get_trace_manager",
    
    # Logging
    "configure_logging",
    "get_logger",
    "get_audit_logger",
    "LogContext",
    "PerformanceLogger",
    "RequestLogger",
    "set_correlation_id",
    "set_plan_id",
    "set_pipeline_id",
    "get_correlation_id",
    "get_plan_id",
    "get_pipeline_id",
    
    # Metrics
    "MetricsCollector",
    "MetricType",
    "Metric",
    "BusinessMetrics",
    "PerformanceMetrics",
    "get_metrics_collector",
    
    # Error Recovery
    "ErrorRecoveryManager",
    "RecoveryPolicy",
    "ErrorContext",
    "RecoveryResult",
    "RecoveryAction",
    "ErrorSeverity",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitBreakerOpenError",
    "CircuitBreakerRegistry",
    "get_error_recovery_manager",
    
    # DI
    "DependencyContainer",
    "Scope",
    "ScopeContext",
    "IDependencyContainer",
    "DependencyNotFoundError",
    "CircularDependencyError",
    "Lazy",
    "LazyResolution",
    "get_container",
    "reset_container",
    "injectable",
    "inject",
    
    # Plugins
    "PluginManager",
    "Plugin",
    "PluginState",
    "PluginHook",
    "PluginMetadata",
    "get_plugin_manager",
    "plugin",
    
    # Registry
    "ServiceRegistry",
    "VersionedServiceRegistry",
    "Registry",
    "RegistryScope",
    "ServiceRegistration",
    "ServiceHealth",
    "ServiceDiscovery",
    "ServiceNotFoundError",
    "ServiceAlreadyRegisteredError",
    "get_registry",
    "get_versioned_registry",
    "registered_service",
    "injectable_service",
]
