"""
Cognitive Event System - Storage and retrieval of structured cognitive events.

This module manages the lifecycle of cognitive events, providing storage, retrieval,
and querying capabilities for the system's cognitive experiences.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class CognitiveEventStore:
    """
    In-memory store for cognitive events (can be extended to use a database).
    
    This is a temporary implementation that stores events in memory.
    In production, this should be backed by a persistent database.
    """
    
    def __init__(self):
        """Initialize the event store."""
        self.events: Dict[str, Dict[str, Any]] = {}
        self.events_by_type: Dict[str, List[str]] = defaultdict(list)
        self.events_by_timestamp: List[tuple] = []
        self.logger = logging.getLogger(__name__)
    
    def store_event(self, event_data: Dict[str, Any]) -> str:
        """
        Store a cognitive event.
        
        Args:
            event_data: Dictionary containing the event data
            
        Returns:
            The event ID
        """
        event_id = event_data.get('event_id', str(uuid.uuid4()))
        self.events[event_id] = event_data
        
        # Index by type
        event_type = event_data.get('event_type', 'unknown')
        self.events_by_type[event_type].append(event_id)
        
        # Index by timestamp
        timestamp = event_data.get('timestamp', datetime.utcnow().isoformat())
        self.events_by_timestamp.append((timestamp, event_id))
        self.events_by_timestamp.sort()
        
        self.logger.info(f"Stored event {event_id} of type {event_type}")
        return event_id
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cognitive event by ID.
        
        Args:
            event_id: The ID of the event to retrieve
            
        Returns:
            The event data, or None if not found
        """
        return self.events.get(event_id)
    
    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """
        Retrieve all events of a specific type.
        
        Args:
            event_type: The type of events to retrieve
            
        Returns:
            List of events of the specified type
        """
        event_ids = self.events_by_type.get(event_type, [])
        return [self.events[event_id] for event_id in event_ids if event_id in self.events]
    
    def get_events_by_time_range(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve events within a specific time range.
        
        Args:
            start_time: Start of the time range
            end_time: End of the time range
            
        Returns:
            List of events within the time range
        """
        result = []
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()
        
        for timestamp, event_id in self.events_by_timestamp:
            if start_iso <= timestamp <= end_iso:
                result.append(self.events[event_id])
        
        return result
    
    def get_all_events(self) -> List[Dict[str, Any]]:
        """
        Retrieve all stored events.
        
        Returns:
            List of all events
        """
        return list(self.events.values())
    
    def delete_event(self, event_id: str) -> bool:
        """
        Delete a cognitive event.
        
        Args:
            event_id: The ID of the event to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        if event_id in self.events:
            event_data = self.events[event_id]
            del self.events[event_id]
            
            # Remove from type index
            event_type = event_data.get('event_type', 'unknown')
            if event_id in self.events_by_type[event_type]:
                self.events_by_type[event_type].remove(event_id)
            
            # Remove from timestamp index
            self.events_by_timestamp = [
                (ts, eid) for ts, eid in self.events_by_timestamp if eid != event_id
            ]
            
            self.logger.info(f"Deleted event {event_id}")
            return True
        
        return False


class CognitiveEventSystem:
    """
    Manages the creation, storage, and retrieval of cognitive events.
    
    This system acts as the central hub for all cognitive events within
    the Hajeen Cognitive Operating System.
    """
    
    def __init__(self, store: Optional[CognitiveEventStore] = None):
        """
        Initialize the Cognitive Event System.
        
        Args:
            store: Optional custom event store (defaults to in-memory store)
        """
        self.store = store or CognitiveEventStore()
        self.logger = logging.getLogger(__name__)
    
    def create_event(self, raw_input: str, event_type: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a new cognitive event.
        
        Args:
            raw_input: The raw input that triggered the event
            event_type: The type of cognitive event
            context: Optional context information
            
        Returns:
            The created event data
        """
        event = {
            'event_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'raw_input': raw_input,
            'context': context or {},
            'status': 'created'
        }
        
        self.logger.info(f"Created cognitive event {event['event_id']} of type {event_type}")
        return event
    
    def store_event(self, event: Dict[str, Any]) -> str:
        """
        Store a cognitive event in the event system.
        
        Args:
            event: The event to store
            
        Returns:
            The event ID
        """
        event_id = self.store.store_event(event)
        self.logger.info(f"Stored cognitive event {event_id}")
        return event_id
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cognitive event by ID.
        
        Args:
            event_id: The ID of the event
            
        Returns:
            The event data, or None if not found
        """
        return self.store.get_event(event_id)
    
    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """
        Retrieve all events of a specific type.
        
        Args:
            event_type: The type of events to retrieve
            
        Returns:
            List of events of the specified type
        """
        return self.store.get_events_by_type(event_type)
    
    def get_events_by_time_range(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve events within a specific time range.
        
        Args:
            start_time: Start of the time range
            end_time: End of the time range
            
        Returns:
            List of events within the time range
        """
        return self.store.get_events_by_time_range(start_time, end_time)
    
    def get_all_events(self) -> List[Dict[str, Any]]:
        """
        Retrieve all stored events.
        
        Returns:
            List of all events
        """
        return self.store.get_all_events()
    
    def search_events(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for events based on criteria.
        
        Args:
            query: Search criteria (e.g., {'event_type': 'fact_extraction', 'min_confidence': 0.7})
            
        Returns:
            List of events matching the criteria
        """
        results = []
        all_events = self.store.get_all_events()
        
        for event in all_events:
            match = True
            
            # Check event type
            if 'event_type' in query and event.get('event_type') != query['event_type']:
                match = False
            
            # Check confidence level
            if 'min_confidence' in query and event.get('confidence_level', 0) < query['min_confidence']:
                match = False
            
            # Check for keywords in raw input
            if 'keywords' in query:
                keywords = query['keywords']
                raw_input = event.get('raw_input', '').lower()
                if not any(keyword.lower() in raw_input for keyword in keywords):
                    match = False
            
            if match:
                results.append(event)
        
        self.logger.info(f"Found {len(results)} events matching query")
        return results
    
    def get_event_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored events.
        
        Returns:
            Dictionary containing event statistics
        """
        all_events = self.store.get_all_events()
        
        stats = {
            'total_events': len(all_events),
            'events_by_type': {},
            'average_confidence': 0.0,
            'earliest_event': None,
            'latest_event': None
        }
        
        if not all_events:
            return stats
        
        # Count by type
        for event in all_events:
            event_type = event.get('event_type', 'unknown')
            stats['events_by_type'][event_type] = stats['events_by_type'].get(event_type, 0) + 1
        
        # Calculate average confidence
        confidences = [event.get('confidence_level', 0.5) for event in all_events]
        stats['average_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Get earliest and latest events
        timestamps = [event.get('timestamp') for event in all_events if event.get('timestamp')]
        if timestamps:
            timestamps.sort()
            stats['earliest_event'] = timestamps[0]
            stats['latest_event'] = timestamps[-1]
        
        return stats
    
    def export_events(self, event_ids: Optional[List[str]] = None) -> str:
        """
        Export events as JSON.
        
        Args:
            event_ids: Optional list of specific event IDs to export (defaults to all)
            
        Returns:
            JSON string containing the events
        """
        if event_ids:
            events = [self.store.get_event(eid) for eid in event_ids if self.store.get_event(eid)]
        else:
            events = self.store.get_all_events()
        
        return json.dumps(events, indent=2, default=str)
    
    def delete_event(self, event_id: str) -> bool:
        """
        Delete a cognitive event.
        
        Args:
            event_id: The ID of the event to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        return self.store.delete_event(event_id)
