"""
Event Driven Architecture
========================

Provides event-driven architecture components:
- Event Bus: Central event dispatcher
- Event Store: Persistent event storage
- Event Replay: Replay events from store
- Event Subscribers: Reactive event handlers

Usage:
    # Subscribe to events
    @event_bus.subscribe("request.processed")
    def on_request_processed(event):
        print(f"Request processed: {event.data}")
    
    # Publish events
    event_bus.publish("request.processed", {"request_id": "123"})
    
    # Async subscribers
    @event_bus.subscribe_async("request.failed")
    async def handle_failure(event):
        await send_alert(event.data)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import (
    Any, Callable, Dict, List, Optional, Set, Type, 
    TypeVar, Union, Awaitable, Generic
)
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import defaultdict
import threading
from contextvars import ContextVar
import traceback

logger = logging.getLogger(__name__)

T = TypeVar('T')


class EventPriority(Enum):
    """Event priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Event:
    """
    Base event class.
    
    Attributes:
        id: Unique event ID
        type: Event type (topic)
        data: Event payload
        timestamp: Event timestamp
        source: Event source
        priority: Event priority
        correlation_id: For tracing related events
        causation_id: ID of the event that caused this event
        metadata: Additional metadata
    """
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.source:
            self.source = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary."""
        result = asdict(self)
        result['timestamp'] = datetime.fromtimestamp(self.timestamp).isoformat()
        result['priority'] = self.priority.value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Event:
        """Deserialize event from dictionary."""
        if isinstance(data.get('timestamp'), str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp']).timestamp()
        if isinstance(data.get('priority'), str):
            data['priority'] = EventPriority(data['priority'])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def with_correlation(self, correlation_id: str) -> Event:
        """Create new event with correlation ID."""
        self.correlation_id = correlation_id
        return self


@dataclass
class AsyncEvent(Event):
    """Event with async handling support."""
    pass


class EventHandler:
    """Base event handler."""
    
    def __init__(
        self,
        handler: Callable,
        async_handler: Optional[Callable] = None,
        filter: Optional[Callable[[Event], bool]] = None,
        priority: int = 0
    ):
        self.handler = handler
        self.async_handler = async_handler
        self.filter = filter
        self.priority = priority
        self.handled_count = 0
        self.error_count = 0
        self.last_error: Optional[Exception] = None
        self.is_async = asyncio.iscoroutinefunction(handler) or async_handler is not None
    
    async def handle(self, event: Event) -> bool:
        """Handle an event."""
        try:
            # Apply filter
            if self.filter and not self.filter(event):
                return True  # Skip, but don't fail
            
            # Handle
            if self.async_handler:
                await self.async_handler(event)
            elif asyncio.iscoroutinefunction(self.handler):
                await self.handler(event)
            else:
                self.handler(event)
            
            self.handled_count += 1
            return True
            
        except Exception as e:
            self.error_count += 1
            self.last_error = e
            logger.error(f"Event handler error: {e}")
            return False


class EventBus:
    """
    Central event bus for publish/subscribe pattern.
    
    Features:
    - Topic-based subscriptions
    - Wildcard subscriptions
    - Priority handling
    - Async support
    - Event filtering
    - Dead letter queue
    """
    
    _instance: Optional[EventBus] = None
    
    def __init__(self):
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._event_store: Optional[EventStore] = None
        self._dead_letter_queue: List[Event] = []
        self._max_dead_letter_size = 1000
        self._global_handlers: List[EventHandler] = []
        self._stats = {
            "published": 0,
            "handled": 0,
            "errors": 0,
            "dead_letters": 0
        }
    
    @classmethod
    def get_instance(cls) -> EventBus:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_event_store(self, store: EventStore):
        """Set event store for persistence."""
        self._event_store = store
    
    def subscribe(
        self,
        topic: str,
        handler: Callable[[Event], Any],
        filter: Optional[Callable[[Event], bool]] = None,
        priority: int = 0
    ) -> EventHandler:
        """
        Subscribe to an event topic.
        
        Args:
            topic: Event topic (supports wildcards like "user.*")
            handler: Event handler function
            filter: Optional filter function
            priority: Handler priority (higher = first)
            
        Returns:
            EventHandler instance
        """
        event_handler = EventHandler(handler=handler, filter=filter, priority=priority)
        
        with self._lock:
            if '*' in topic:
                self._wildcard_subscribers[topic].append(event_handler)
                self._wildcard_subscribers[topic].sort(key=lambda h: -h.priority)
            else:
                self._subscribers[topic].append(event_handler)
                self._subscribers[topic].sort(key=lambda h: -h.priority)
        
        logger.debug(f"Subscribed to {topic}")
        return event_handler
    
    def subscribe_async(
        self,
        topic: str,
        handler: Callable[[Event], Awaitable[Any]],
        filter: Optional[Callable[[Event], bool]] = None,
        priority: int = 0
    ) -> EventHandler:
        """Subscribe with async handler."""
        event_handler = EventHandler(
            handler=handler,
            async_handler=handler,
            filter=filter,
            priority=priority
        )
        
        with self._lock:
            if '*' in topic:
                self._wildcard_subscribers[topic].append(event_handler)
            else:
                self._subscribers[topic].append(event_handler)
        
        return event_handler
    
    def subscribe_global(
        self,
        handler: Callable[[Event], Any],
        filter: Optional[Callable[[Event], bool]] = None
    ) -> EventHandler:
        """Subscribe to all events."""
        event_handler = EventHandler(handler=handler, filter=filter)
        self._global_handlers.append(event_handler)
        return event_handler
    
    def unsubscribe(self, topic: str, handler: EventHandler) -> bool:
        """Unsubscribe from a topic."""
        with self._lock:
            if topic in self._subscribers:
                try:
                    self._subscribers[topic].remove(handler)
                    return True
                except ValueError:
                    pass
            
            if topic in self._wildcard_subscribers:
                try:
                    self._wildcard_subscribers[topic].remove(handler)
                    return True
                except ValueError:
                    pass
        
        return False
    
    def publish(
        self,
        topic: str,
        data: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> Event:
        """
        Publish an event.
        
        Args:
            topic: Event topic
            data: Event payload
            priority: Event priority
            correlation_id: For tracing
            **kwargs: Additional event data
            
        Returns:
            Published Event
        """
        event = Event(
            type=topic,
            data=data or kwargs,
            priority=priority,
            correlation_id=correlation_id
        )
        
        return self._publish_event(event)
    
    def _publish_event(self, event: Event) -> Event:
        """Internal event publishing."""
        self._stats["published"] += 1
        
        # Store event
        if self._event_store:
            try:
                self._event_store.store(event)
            except Exception as e:
                logger.error(f"Failed to store event: {e}")
        
        # Get handlers
        handlers = self._get_handlers(event.type)
        handlers.extend(self._global_handlers)
        
        if not handlers:
            return event
        
        # Handle synchronously
        for handler in handlers:
            if handler.is_async:
                # Don't await in sync publish
                asyncio.create_task(self._safe_handle(handler, event))
            else:
                self._safe_handle(handler, event)
        
        return event
    
    async def publish_async(
        self,
        topic: str,
        data: Optional[Dict[str, Any]] = None,
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> Event:
        """Publish event asynchronously."""
        event = Event(
            type=topic,
            data=data or kwargs,
            priority=priority,
            correlation_id=correlation_id
        )
        
        return self._publish_event(event)
    
    async def _safe_handle(self, handler: EventHandler, event: Event):
        """Safely handle an event."""
        try:
            if handler.async_handler:
                await handler.async_handler(event)
            elif asyncio.iscoroutinefunction(handler.handler):
                await handler.handler(event)
            else:
                handler.handler(event)
            
            handler.handled_count += 1
            self._stats["handled"] += 1
            
        except Exception as e:
            handler.error_count += 1
            handler.last_error = e
            self._stats["errors"] += 1
            logger.error(f"Event handler error: {e}\n{traceback.format_exc()}")
            
            # Add to dead letter queue
            self._add_to_dead_letter(event, str(e))
    
    def _safe_handle_sync(self, handler: EventHandler, event: Event):
        """Safely handle event synchronously."""
        try:
            if handler.filter and not handler.filter(event):
                return
            
            handler.handler(event)
            handler.handled_count += 1
            self._stats["handled"] += 1
            
        except Exception as e:
            handler.error_count += 1
            handler.last_error = e
            self._stats["errors"] += 1
            logger.error(f"Event handler error: {e}")
            self._add_to_dead_letter(event, str(e))
    
    def _get_handlers(self, topic: str) -> List[EventHandler]:
        """Get all handlers for a topic, including wildcard matches."""
        handlers = list(self._subscribers.get(topic, []))
        
        # Check wildcard patterns
        for pattern, pattern_handlers in self._wildcard_subscribers.items():
            if self._match_wildcard(topic, pattern):
                handlers.extend(pattern_handlers)
        
        # Sort by priority
        handlers.sort(key=lambda h: -h.priority)
        return handlers
    
    def _match_wildcard(self, topic: str, pattern: str) -> bool:
        """Check if topic matches wildcard pattern."""
        import fnmatch
        return fnmatch.fnmatch(topic, pattern)
    
    def _add_to_dead_letter(self, event: Event, error: str):
        """Add failed event to dead letter queue."""
        event.metadata['error'] = error
        event.metadata['dead_letter_at'] = datetime.utcnow().isoformat()
        
        with self._lock:
            self._dead_letter_queue.append(event)
            if len(self._dead_letter_queue) > self._max_dead_letter_size:
                self._dead_letter_queue.pop(0)
        
        self._stats["dead_letters"] += 1
    
    def get_dead_letters(self) -> List[Event]:
        """Get all dead letter events."""
        with self._lock:
            return list(self._dead_letter_queue)
    
    def clear_dead_letters(self):
        """Clear dead letter queue."""
        with self._lock:
            self._dead_letter_queue.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics."""
        with self._lock:
            return {
                **self._stats,
                "topics": len(self._subscribers),
                "wildcard_patterns": len(self._wildcard_subscribers),
                "dead_letters": len(self._dead_letter_queue)
            }
    
    def get_handler_stats(self, topic: str) -> List[Dict[str, Any]]:
        """Get handler statistics for a topic."""
        handlers = self._get_handlers(topic)
        return [
            {
                "handled_count": h.handled_count,
                "error_count": h.error_count,
                "last_error": str(h.last_error) if h.last_error else None,
                "is_async": h.is_async,
                "priority": h.priority
            }
            for h in handlers
        ]


class EventStore:
    """
    Persistent event store.
    
    Stores events for:
    - Event replay
    - Audit trail
    - Event sourcing
    - Debugging
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_events: int = 100000
    ):
        self._storage_path = storage_path
        self._max_events = max_events
        self._events: List[Event] = []
        self._lock = threading.Lock()
        self._index: Dict[str, List[int]] = defaultdict(list)  # topic -> event indices
    
    def store(self, event: Event):
        """Store an event."""
        with self._lock:
            self._events.append(event)
            
            # Update index
            self._index[event.type].append(len(self._events) - 1)
            
            # Trim if needed
            if len(self._events) > self._max_events:
                self._trim_events()
            
            # Persist
            if self._storage_path:
                self._persist()
    
    def get(
        self,
        topic: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Event]:
        """Retrieve events."""
        with self._lock:
            if topic:
                indices = self._index.get(topic, [])
                events = [self._events[i] for i in indices[-limit:]]
            else:
                events = self._events[-limit:]
            
            if since:
                events = [
                    e for e in events
                    if datetime.fromtimestamp(e.timestamp) >= since
                ]
            
            return events
    
    def get_by_correlation(self, correlation_id: str) -> List[Event]:
        """Get events by correlation ID."""
        with self._lock:
            return [
                e for e in self._events
                if e.correlation_id == correlation_id
            ]
    
    def replay(
        self,
        topic: str,
        since: Optional[datetime] = None,
        handler: Optional[Callable[[Event], Any]] = None
    ) -> List[Event]:
        """
        Replay events from store.
        
        Args:
            topic: Event topic to replay
            since: Replay events since this time
            handler: Optional handler to call for each event
            
        Returns:
            List of replayed events
        """
        events = self.get(topic, since=since)
        
        if handler:
            for event in events:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Replay handler error: {e}")
        
        return events
    
    def _trim_events(self):
        """Trim old events to maintain max size."""
        trim_count = len(self._events) - self._max_events
        if trim_count > 0:
            self._events = self._events[trim_count:]
            
            # Rebuild index
            self._index.clear()
            for i, event in enumerate(self._events):
                self._index[event.type].append(i)
    
    def _persist(self):
        """Persist events to storage."""
        # Implementation depends on storage backend
        # For now, just log
        logger.debug(f"Persisting {len(self._events)} events to {self._storage_path}")
    
    def clear(self):
        """Clear all stored events."""
        with self._lock:
            self._events.clear()
            self._index.clear()
    
    def __len__(self) -> int:
        return len(self._events)


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus.get_instance()
    return _event_bus


# Decorators for convenience
def on_event(topic: str, priority: int = 0):
    """
    Decorator to subscribe to an event.
    
    Usage:
        @on_event("request.processed")
        def handle_request(event):
            print(f"Request: {event.data}")
    """
    def decorator(func: Callable):
        event_bus = get_event_bus()
        event_bus.subscribe(topic, func, priority=priority)
        return func
    return decorator


def on_event_async(topic: str, priority: int = 0):
    """
    Decorator to subscribe to an async event handler.
    
    Usage:
        @on_event_async("request.failed")
        async def handle_failure(event):
            await send_alert(event.data)
    """
    def decorator(func: Callable):
        event_bus = get_event_bus()
        event_bus.subscribe_async(topic, func, priority=priority)
        return func
    return decorator


# Common event types
class BrainEvents:
    """Brain-related event types."""
    REQUEST_RECEIVED = "brain.request.received"
    REQUEST_PROCESSED = "brain.request.processed"
    REQUEST_FAILED = "brain.request.failed"
    GOAL_ANALYZED = "brain.goal.analyzed"
    REASONING_STARTED = "brain.reasoning.started"
    REASONING_COMPLETED = "brain.reasoning.completed"
    MODEL_SELECTED = "brain.model.selected"
    RESPONSE_GENERATED = "brain.response.generated"
    MEMORY_UPDATED = "brain.memory.updated"
    KNOWLEDGE_UPDATED = "brain.knowledge.updated"


class SystemEvents:
    """System event types."""
    STARTUP = "system.startup"
    SHUTDOWN = "system.shutdown"
    HEALTH_CHECK = "system.health"
    METRICS_COLLECTED = "system.metrics"


class SecurityEvents:
    """Security event types."""
    AUTH_SUCCESS = "security.auth.success"
    AUTH_FAILURE = "security.auth.failure"
    RATE_LIMITED = "security.rate_limited"
    POLICY_VIOLATION = "security.policy_violation"
