"""
Cognitive DNA - Metadata and evolutionary history for concepts.

Each concept possesses a cognitive DNA that tracks its origin, quality, stability,
and evolution over time, enabling detailed understanding of knowledge provenance
and reliability.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CognitiveDNA:
    """
    Represents the cognitive DNA of a concept, containing metadata about its
    origin, quality, and evolutionary history.
    """
    dna_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    concept_id: str = ""
    
    # Knowledge Source Information
    knowledge_source: List[str] = field(default_factory=list)
    num_sources: int = 0
    source_quality: float = 0.5  # 0.0 to 1.0
    
    # Confidence and Stability
    confidence_level: float = 0.5  # 0.0 to 1.0
    change_rate: float = 0.0  # How often the concept changes
    stability: float = 0.5  # How stable/consistent the concept is
    
    # Relationships and Experiences
    causal_relationships: List[Dict[str, Any]] = field(default_factory=list)
    associated_experiences: List[str] = field(default_factory=list)  # event_ids
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    evolution_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_updated'] = self.last_updated.isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def add_source(self, source: str, quality: float = 0.7) -> None:
        """Add a knowledge source."""
        if source not in self.knowledge_source:
            self.knowledge_source.append(source)
            self.num_sources += 1
            
            # Update source quality
            if self.num_sources > 0:
                self.source_quality = (self.source_quality * (self.num_sources - 1) + quality) / self.num_sources
            
            self.last_updated = datetime.utcnow()
            logger.info(f"Added source {source} to DNA for concept {self.concept_id}")
    
    def add_causal_relationship(self, relationship: Dict[str, Any]) -> None:
        """Add a causal relationship."""
        self.causal_relationships.append(relationship)
        self.last_updated = datetime.utcnow()
    
    def add_experience(self, event_id: str) -> None:
        """Associate an experience with this concept."""
        if event_id not in self.associated_experiences:
            self.associated_experiences.append(event_id)
            self.last_updated = datetime.utcnow()
    
    def record_evolution(self, change_type: str, old_value: Any, new_value: Any, reason: str = "") -> None:
        """Record an evolutionary change."""
        evolution_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'change_type': change_type,
            'old_value': old_value,
            'new_value': new_value,
            'reason': reason
        }
        self.evolution_history.append(evolution_record)
        self.last_updated = datetime.utcnow()


class CognitiveDNAStore:
    """
    In-memory store for cognitive DNA (can be extended to use a database).
    """
    
    def __init__(self):
        """Initialize the DNA store."""
        self.dna_records: Dict[str, CognitiveDNA] = {}
        self.dna_by_concept: Dict[str, str] = {}  # concept_id -> dna_id
        self.logger = logging.getLogger(__name__)
    
    def store_dna(self, dna: CognitiveDNA) -> str:
        """Store a cognitive DNA record."""
        self.dna_records[dna.dna_id] = dna
        self.dna_by_concept[dna.concept_id] = dna.dna_id
        self.logger.info(f"Stored DNA {dna.dna_id} for concept {dna.concept_id}")
        return dna.dna_id
    
    def get_dna(self, dna_id: str) -> Optional[CognitiveDNA]:
        """Retrieve a DNA record by ID."""
        return self.dna_records.get(dna_id)
    
    def get_dna_by_concept(self, concept_id: str) -> Optional[CognitiveDNA]:
        """Retrieve a DNA record by concept ID."""
        dna_id = self.dna_by_concept.get(concept_id)
        if dna_id:
            return self.dna_records.get(dna_id)
        return None
    
    def get_all_dna(self) -> List[CognitiveDNA]:
        """Retrieve all DNA records."""
        return list(self.dna_records.values())
    
    def delete_dna(self, dna_id: str) -> bool:
        """Delete a DNA record."""
        if dna_id in self.dna_records:
            dna = self.dna_records[dna_id]
            del self.dna_records[dna_id]
            if dna.concept_id in self.dna_by_concept:
                del self.dna_by_concept[dna.concept_id]
            self.logger.info(f"Deleted DNA {dna_id}")
            return True
        return False


class CognitiveDNAManager:
    """
    Manages the creation, storage, and retrieval of cognitive DNA records.
    
    The Cognitive DNA Manager provides detailed metadata about concept origins,
    quality, stability, and evolutionary history.
    """
    
    def __init__(self, store: Optional[CognitiveDNAStore] = None):
        """
        Initialize the Cognitive DNA Manager.
        
        Args:
            store: Optional custom DNA store
        """
        self.store = store or CognitiveDNAStore()
        self.logger = logging.getLogger(__name__)
    
    def create_dna(self, concept_id: str, source_info: Optional[Dict[str, Any]] = None) -> CognitiveDNA:
        """
        Create a new cognitive DNA record for a concept.
        
        Args:
            concept_id: The ID of the concept
            source_info: Optional source information
            
        Returns:
            The created CognitiveDNA object
        """
        dna = CognitiveDNA(concept_id=concept_id)
        
        if source_info:
            if 'source' in source_info:
                quality = source_info.get('quality', 0.7)
                dna.add_source(source_info['source'], quality)
            
            if 'confidence' in source_info:
                dna.confidence_level = source_info['confidence']
            
            if 'stability' in source_info:
                dna.stability = source_info['stability']
        
        self.store.store_dna(dna)
        self.logger.info(f"Created DNA for concept {concept_id}")
        return dna
    
    def get_dna(self, dna_id: str) -> Optional[CognitiveDNA]:
        """
        Retrieve a DNA record by ID.
        
        Args:
            dna_id: The ID of the DNA record
            
        Returns:
            The CognitiveDNA object, or None if not found
        """
        return self.store.get_dna(dna_id)
    
    def get_dna_by_concept(self, concept_id: str) -> Optional[CognitiveDNA]:
        """
        Retrieve a DNA record by concept ID.
        
        Args:
            concept_id: The ID of the concept
            
        Returns:
            The CognitiveDNA object, or None if not found
        """
        return self.store.get_dna_by_concept(concept_id)
    
    def update_dna(self, dna_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a DNA record.
        
        Args:
            dna_id: The ID of the DNA record
            updates: Dictionary of fields to update
            
        Returns:
            True if update was successful, False otherwise
        """
        dna = self.store.get_dna(dna_id)
        if not dna:
            self.logger.warning(f"DNA {dna_id} not found")
            return False
        
        allowed_fields = {
            'confidence_level', 'change_rate', 'stability',
            'source_quality', 'num_sources'
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                old_value = getattr(dna, field)
                setattr(dna, field, value)
                dna.record_evolution(field, old_value, value)
        
        self.logger.info(f"Updated DNA {dna_id}")
        return True
    
    def add_source_to_dna(self, dna_id: str, source: str, quality: float = 0.7) -> bool:
        """
        Add a source to a DNA record.
        
        Args:
            dna_id: The ID of the DNA record
            source: The source to add
            quality: The quality of the source (0.0 to 1.0)
            
        Returns:
            True if successful, False otherwise
        """
        dna = self.store.get_dna(dna_id)
        if not dna:
            return False
        
        dna.add_source(source, quality)
        return True
    
    def add_causal_relationship_to_dna(self, dna_id: str, relationship: Dict[str, Any]) -> bool:
        """
        Add a causal relationship to a DNA record.
        
        Args:
            dna_id: The ID of the DNA record
            relationship: The causal relationship to add
            
        Returns:
            True if successful, False otherwise
        """
        dna = self.store.get_dna(dna_id)
        if not dna:
            return False
        
        dna.add_causal_relationship(relationship)
        return True
    
    def add_experience_to_dna(self, dna_id: str, event_id: str) -> bool:
        """
        Associate an experience with a DNA record.
        
        Args:
            dna_id: The ID of the DNA record
            event_id: The ID of the cognitive event
            
        Returns:
            True if successful, False otherwise
        """
        dna = self.store.get_dna(dna_id)
        if not dna:
            return False
        
        dna.add_experience(event_id)
        return True
    
    def get_dna_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored DNA records.
        
        Returns:
            Dictionary containing DNA statistics
        """
        all_dna = self.store.get_all_dna()
        
        stats = {
            'total_dna_records': len(all_dna),
            'average_confidence': 0.0,
            'average_stability': 0.0,
            'average_source_quality': 0.0,
            'total_sources': 0,
            'total_causal_relationships': 0,
            'total_experiences': 0
        }
        
        if not all_dna:
            return stats
        
        confidences = [dna.confidence_level for dna in all_dna]
        stabilities = [dna.stability for dna in all_dna]
        source_qualities = [dna.source_quality for dna in all_dna]
        
        stats['average_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
        stats['average_stability'] = sum(stabilities) / len(stabilities) if stabilities else 0.0
        stats['average_source_quality'] = sum(source_qualities) / len(source_qualities) if source_qualities else 0.0
        
        stats['total_sources'] = sum(dna.num_sources for dna in all_dna)
        stats['total_causal_relationships'] = sum(len(dna.causal_relationships) for dna in all_dna)
        stats['total_experiences'] = sum(len(dna.associated_experiences) for dna in all_dna)
        
        return stats
    
    def get_high_confidence_concepts(self, threshold: float = 0.8) -> List[CognitiveDNA]:
        """
        Get DNA records for concepts with high confidence.
        
        Args:
            threshold: Confidence threshold (0.0 to 1.0)
            
        Returns:
            List of high-confidence DNA records
        """
        all_dna = self.store.get_all_dna()
        return [dna for dna in all_dna if dna.confidence_level >= threshold]
    
    def get_unstable_concepts(self, threshold: float = 0.5) -> List[CognitiveDNA]:
        """
        Get DNA records for concepts with low stability.
        
        Args:
            threshold: Stability threshold (0.0 to 1.0)
            
        Returns:
            List of unstable DNA records
        """
        all_dna = self.store.get_all_dna()
        return [dna for dna in all_dna if dna.stability < threshold]
    
    def export_dna_records(self, dna_ids: Optional[List[str]] = None) -> str:
        """
        Export DNA records as JSON.
        
        Args:
            dna_ids: Optional list of specific DNA IDs to export
            
        Returns:
            JSON string containing the DNA records
        """
        if dna_ids:
            records = [self.store.get_dna(dna_id) for dna_id in dna_ids if self.store.get_dna(dna_id)]
        else:
            records = self.store.get_all_dna()
        
        return json.dumps([dna.to_dict() for dna in records], indent=2, default=str)
