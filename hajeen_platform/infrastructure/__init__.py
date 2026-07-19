"""
HAJEEN PLATFORM - Infrastructure Layer
====================================

Production-grade infrastructure components for the Hajeen AI Platform.

Components:
    - Configuration Management (config/)
    - Dependency Injection (di/)
    - Service Registries (registry/)
    - Event Driven Architecture (events/)
    - Background Workers (workers/)
    - Observability (observability/)
    - Reliability (reliability/)

Usage:
    from infrastructure import get_config, get_event_bus, get_logger
    
    # Configuration
    config = get_config()
    api_key = config.get("OPENAI_API_KEY", secret=True)
    
    # Event Bus
    event_bus = get_event_bus()
    event_bus.subscribe("request.processed", my_handler)
    event_bus.publish("request.processed", {"id": "123"})
    
    # Logging
    logger = get_logger(__name__)
    logger.info("Processing request", request_id="123")
"""

__version__ = "1.0.0"
__all__ = [
    # Config
    "get_config",
    "Config",
    "ConfigurationError",
    
    # DI
    "get_container",
    "Container",
    "ScopedContainer",
    "inject",
    "injectable",
    "Lifetime",
    
    # Registries
    "ServiceRegistry",
    "ModelRegistry",
    "ToolRegistry",
    "PromptRegistry",
    "WorkflowRegistry",
    "DatasetRegistry",
    "RegistryCategory",
    "get_model_registry",
    "get_tool_registry",
    "get_prompt_registry",
    "get_workflow_registry",
    "get_dataset_registry",
    
    # Events
    "EventBus",
    "Event",
    "EventStore",
    "EventPriority",
    "get_event_bus",
    "on_event",
    "on_event_async",
    "BrainEvents",
    "SystemEvents",
    "SecurityEvents",
    
    # Workers
    "TaskQueue",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "get_task_queue",
    
    # Observability
    "get_logger",
    "StructuredLogger",
    "get_tracer",
    "Tracer",
    "Span",
    "get_metrics",
    "get_health_registry",
    "increment",
    "gauge",
    "timing",
    
    # Reliability
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "circuit_breaker",
    "retry",
    "BackoffStrategy",
    "RateLimiter",
    "rate_limit",
    "timeout",
    "GracefulShutdown",
    "BackpressureLimiter",
]

# Import all components
from .config import get_config, Config, ConfigurationError
from .di import (
    get_container, Container, ScopedContainer,
    inject, injectable, Lifetime
)
from .registry import (
    ServiceRegistry, ModelRegistry, ToolRegistry,
    PromptRegistry, WorkflowRegistry, DatasetRegistry,
    RegistryCategory,
    get_model_registry, get_tool_registry, get_prompt_registry,
    get_workflow_registry, get_dataset_registry
)
from .events import (
    EventBus, Event, EventStore, EventPriority,
    get_event_bus, on_event, on_event_async,
    BrainEvents, SystemEvents, SecurityEvents
)
from .workers import (
    TaskQueue, Task, TaskStatus, TaskPriority,
    get_task_queue
)
from .observability import (
    get_logger, StructuredLogger,
    get_tracer, Tracer, Span,
    get_metrics, get_health_registry,
    increment, gauge, timing
)
from .reliability import (
    CircuitBreaker, CircuitBreakerRegistry, CircuitOpenError,
    circuit_breaker, retry, BackoffStrategy,
    RateLimiter, rate_limit, timeout,
    GracefulShutdown, BackpressureLimiter
)


def setup_infrastructure():
    """
    Setup all infrastructure components.
    
    Call this once at application startup.
    """
    # Initialize event store for persistence
    event_store = EventStore()
    event_bus = get_event_bus()
    event_bus.set_event_store(event_store)
    
    # Setup observability handlers
    tracer = get_tracer()
    metrics = get_metrics()
    
    # Add span handler to record traces
    def record_span(span: Span):
        logger.debug(
            f"Trace: {span.trace_id} | "
            f"Span: {span.name} | "
            f"Duration: {span.duration_ms:.2f}ms | "
            f"Status: {span.status}"
        )
    
    tracer.add_span_handler(record_span)
    
    # Add metric handler for logging
    def log_metric(mtype: str, name: str, value: float, tags: dict):
        logger.debug(f"Metric: {mtype} {name}={value} {tags}")
    
    metrics.add_handler(log_metric)
    
    logger.info("Infrastructure setup complete")


def get_infrastructure_stats() -> dict:
    """Get comprehensive infrastructure statistics."""
    from .events import get_event_bus
    from .workers import get_task_queue
    from .observability import get_tracer, get_metrics
    
    event_bus = get_event_bus()
    task_queue = get_task_queue()
    tracer = get_tracer()
    metrics = get_metrics()
    
    return {
        "events": event_bus.get_stats(),
        "tasks": task_queue.get_stats(),
        "tracer": {
            "active_spans": len(tracer._spans),
            "traces": len(set(s.trace_id for s in tracer._spans.values()))
        },
        "metrics": metrics.get_all_metrics(),
        "circuit_breakers": CircuitBreakerRegistry.get_all_stats()
    }
