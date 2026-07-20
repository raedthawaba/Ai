"""
Concept Engine - Management of cognitive concepts and their properties.

The Concept Engine evolves the traditional Knowledge Graph into a dynamic system
of independent cognitive entities, each with rich metadata and evolutionary history.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Concept:
    """
    Represents a cognitive concept with rich metadata and evolutionary history.
    """
    concept_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    definition: str = ""
    
    # Properties and Characteristics
    properties: Dict[str, Any] = field(default_factory=dict)
    causes: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    rules: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    
    # Relationships
    related_concepts: List[str] = field(default_factory=list)  # concept_ids
    
    # Evidence and Confidence
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    
    # History and Evolution
    history: List[Dict[str, Any]] = field(default_factory=list)
    experiences: List[str] = field(default_factory=list)  # event_ids
    evolution_timeline: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    cognitive_dna_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert concept to dictionary."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_updated'] = self.last_updated.isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert concept to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def add_evidence(self, evidence: Dict[str, Any]) -> None:
        """Add evidence supporting this concept."""
        self.evidence.append(evidence)
        self.last_updated = datetime.utcnow()
        logger.info(f"Added evidence to concept {self.name}")
    
    def add_related_concept(self, concept_id: str) -> None:
        """Add a related concept."""
        if concept_id not in self.related_concepts:
            self.related_concepts.append(concept_id)
            self.last_updated = datetime.utcnow()
    
    def add_experience(self, event_id: str) -> None:
        """Associate an experience with this concept."""
        if event_id not in self.experiences:
            self.experiences.append(event_id)
            self.last_updated = datetime.utcnow()
    
    def update_confidence(self, new_confidence: float) -> None:
        """Update the confidence level of this concept."""
        old_confidence = self.confidence
        self.confidence = max(0.0, min(1.0, new_confidence))
        self.last_updated = datetime.utcnow()
        
        # Record in evolution timeline
        self.evolution_timeline.append({
            'timestamp': self.last_updated.isoformat(),
            'change': 'confidence_update',
            'old_value': old_confidence,
            'new_value': self.confidence
        })


class ConceptStore:
    """
    In-memory store for concepts (can be extended to use a database).
    """
    
    def __init__(self):
        """Initialize the concept store."""
        self.concepts: Dict[str, Concept] = {}
        self.concepts_by_name: Dict[str, str] = {}  # name -> concept_id
        self.logger = logging.getLogger(__name__)
    
    def store_concept(self, concept: Concept) -> str:
        """Store a concept."""
        self.concepts[concept.concept_id] = concept
        self.concepts_by_name[concept.name.lower()] = concept.concept_id
        self.logger.info(f"Stored concept {concept.name} with ID {concept.concept_id}")
        return concept.concept_id
    
    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """Retrieve a concept by ID."""
        return self.concepts.get(concept_id)
    
    def get_concept_by_name(self, name: str) -> Optional[Concept]:
        """Retrieve a concept by name."""
        concept_id = self.concepts_by_name.get(name.lower())
        if concept_id:
            return self.concepts.get(concept_id)
        return None
    
    def get_all_concepts(self) -> List[Concept]:
        """Retrieve all concepts."""
        return list(self.concepts.values())
    
    def delete_concept(self, concept_id: str) -> bool:
        """Delete a concept."""
        if concept_id in self.concepts:
            concept = self.concepts[concept_id]
            del self.concepts[concept_id]
            del self.concepts_by_name[concept.name.lower()]
            self.logger.info(f"Deleted concept {concept.name}")
            return True
        return False
    
    def concept_exists(self, concept_id: str) -> bool:
        """Check if a concept exists."""
        return concept_id in self.concepts


class ConceptEngine:
    """
    Manages the lifecycle and properties of cognitive concepts.
    
    The Concept Engine evolves the traditional Knowledge Graph into a dynamic
    system of independent cognitive entities, each with rich metadata and
    evolutionary history.
    """
    
    def __init__(self, store: Optional[ConceptStore] = None):
        """
        Initialize the Concept Engine.
        
        Args:
            store: Optional custom concept store
        """
        self.store = store or ConceptStore()
        self.logger = logging.getLogger(__name__)
    
    def create_concept(self, name: str, definition: str, properties: Optional[Dict[str, Any]] = None) -> Concept:
        """
        Create a new concept.
        
        Args:
            name: Name of the concept
            definition: Definition of the concept
            properties: Optional properties of the concept
            
        Returns:
            The created Concept object
        """
        concept = Concept(
            name=name,
            definition=definition,
            properties=properties or {}
        )
        
        self.store.store_concept(concept)
        self.logger.info(f"Created concept: {name}")
        return concept
    
    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """
        Retrieve a concept by ID.
        
        Args:
            concept_id: The ID of the concept
            
        Returns:
            The Concept object, or None if not found
        """
        return self.store.get_concept(concept_id)
    
    def get_concept_by_name(self, name: str) -> Optional[Concept]:
        """
        Retrieve a concept by name.
        
        Args:
            name: The name of the concept
            
        Returns:
            The Concept object, or None if not found
        """
        return self.store.get_concept_by_name(name)
    
    def update_concept(self, concept_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing concept.
        
        Args:
            concept_id: The ID of the concept to update
            updates: Dictionary of fields to update
            
        Returns:
            True if update was successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            self.logger.warning(f"Concept {concept_id} not found")
            return False
        
        # Update allowed fields
        allowed_fields = {
            'definition', 'properties', 'causes', 'effects', 'rules',
            'exceptions', 'evidence', 'confidence'
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                if field == 'confidence':
                    concept.update_confidence(value)
                else:
                    setattr(concept, field, value)
                    concept.last_updated = datetime.utcnow()
        
        self.logger.info(f"Updated concept {concept.name}")
        return True
    
    def add_cause(self, concept_id: str, cause: str) -> bool:
        """
        Add a cause to a concept.
        
        Args:
            concept_id: The ID of the concept
            cause: The cause to add
            
        Returns:
            True if successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return False
        
        if cause not in concept.causes:
            concept.causes.append(cause)
            concept.last_updated = datetime.utcnow()
        
        return True
    
    def add_effect(self, concept_id: str, effect: str) -> bool:
        """
        Add an effect to a concept.
        
        Args:
            concept_id: The ID of the concept
            effect: The effect to add
            
        Returns:
            True if successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return False
        
        if effect not in concept.effects:
            concept.effects.append(effect)
            concept.last_updated = datetime.utcnow()
        
        return True
    
    def add_rule(self, concept_id: str, rule: str) -> bool:
        """
        Add a rule to a concept.
        
        Args:
            concept_id: The ID of the concept
            rule: The rule to add
            
        Returns:
            True if successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return False
        
        if rule not in concept.rules:
            concept.rules.append(rule)
            concept.last_updated = datetime.utcnow()
        
        return True
    
    def add_exception(self, concept_id: str, exception: str) -> bool:
        """
        Add an exception to a concept.
        
        Args:
            concept_id: The ID of the concept
            exception: The exception to add
            
        Returns:
            True if successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return False
        
        if exception not in concept.exceptions:
            concept.exceptions.append(exception)
            concept.last_updated = datetime.utcnow()
        
        return True
    
    def get_related_concepts(self, concept_id: str) -> List[Concept]:
        """
        Retrieve all concepts related to a given concept.
        
        Args:
            concept_id: The ID of the concept
            
        Returns:
            List of related Concept objects
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return []
        
        related = []
        for related_id in concept.related_concepts:
            related_concept = self.store.get_concept(related_id)
            if related_concept:
                related.append(related_concept)
        
        return related
    
    def link_concepts(self, concept_id_1: str, concept_id_2: str) -> bool:
        """
        Create a bidirectional link between two concepts.
        
        Args:
            concept_id_1: ID of the first concept
            concept_id_2: ID of the second concept
            
        Returns:
            True if successful, False otherwise
        """
        concept1 = self.store.get_concept(concept_id_1)
        concept2 = self.store.get_concept(concept_id_2)
        
        if not concept1 or not concept2:
            return False
        
        concept1.add_related_concept(concept_id_2)
        concept2.add_related_concept(concept_id_1)
        
        self.logger.info(f"Linked concepts {concept1.name} and {concept2.name}")
        return True
    
    def add_evidence(self, concept_id: str, evidence: Dict[str, Any]) -> bool:
        """
        Add evidence to a concept.
        
        Args:
            concept_id: The ID of the concept
            evidence: The evidence to add
            
        Returns:
            True if successful, False otherwise
        """
        concept = self.store.get_concept(concept_id)
        if not concept:
            return False
        
        concept.add_evidence(evidence)
        return True
    
    def get_all_concepts(self) -> List[Concept]:
        """
        Retrieve all concepts.
        
        Returns:
            List of all Concept objects
        """
        return self.store.get_all_concepts()
    
    def get_concept_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about stored concepts.
        
        Returns:
            Dictionary containing concept statistics
        """
        concepts = self.store.get_all_concepts()
        
        stats = {
            'total_concepts': len(concepts),
            'average_confidence': 0.0,
            'concepts_with_evidence': 0,
            'total_relationships': 0
        }
        
        if not concepts:
            return stats
        
        confidences = [c.confidence for c in concepts]
        stats['average_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
        
        stats['concepts_with_evidence'] = sum(1 for c in concepts if c.evidence)
        stats['total_relationships'] = sum(len(c.related_concepts) for c in concepts)
        
        return stats
