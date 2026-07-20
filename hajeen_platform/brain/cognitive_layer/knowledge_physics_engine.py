"""
Knowledge Physics Engine - Discovery and validation of causal laws.

This engine discovers, validates, and models causal relationships within
the knowledge base, enabling the system to understand and predict cause-and-effect
relationships in the world.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CausalStrength(Enum):
    """Enumeration of causal relationship strengths."""
    WEAK = 0.3
    MODERATE = 0.6
    STRONG = 0.8
    VERY_STRONG = 0.95


@dataclass
class CausalLaw:
    """
    Represents a discovered causal law or relationship.
    """
    law_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cause_concept: str = ""
    effect_concept: str = ""
    
    # Relationship Details
    relationship_type: str = "direct_causation"
    description: str = ""
    
    # Strength and Confidence
    strength: float = 0.5  # 0.0 to 1.0
    confidence: float = 0.5  # 0.0 to 1.0
    
    # Evidence
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    supporting_experiments: List[str] = field(default_factory=list)
    
    # Conditions
    conditions: List[str] = field(default_factory=list)  # When the law applies
    exceptions: List[str] = field(default_factory=list)  # When the law doesn't apply
    
    # Timeline
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    last_validated: datetime = field(default_factory=datetime.utcnow)
    validation_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['discovered_at'] = self.discovered_at.isoformat()
        data['last_validated'] = self.last_validated.isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    def add_evidence(self, evidence: Dict[str, Any]) -> None:
        """Add supporting evidence."""
        self.evidence.append(evidence)
        self.last_validated = datetime.utcnow()
    
    def validate(self) -> None:
        """Record a validation of this causal law."""
        self.validation_count += 1
        self.last_validated = datetime.utcnow()


class CausalLawStore:
    """
    In-memory store for causal laws (can be extended to use a database).
    """
    
    def __init__(self):
        """Initialize the causal law store."""
        self.laws: Dict[str, CausalLaw] = {}
        self.laws_by_cause: Dict[str, List[str]] = {}  # cause -> [law_ids]
        self.laws_by_effect: Dict[str, List[str]] = {}  # effect -> [law_ids]
        self.logger = logging.getLogger(__name__)
    
    def store_law(self, law: CausalLaw) -> str:
        """Store a causal law."""
        self.laws[law.law_id] = law
        
        # Index by cause
        if law.cause_concept not in self.laws_by_cause:
            self.laws_by_cause[law.cause_concept] = []
        self.laws_by_cause[law.cause_concept].append(law.law_id)
        
        # Index by effect
        if law.effect_concept not in self.laws_by_effect:
            self.laws_by_effect[law.effect_concept] = []
        self.laws_by_effect[law.effect_concept].append(law.law_id)
        
        self.logger.info(f"Stored causal law {law.law_id}: {law.cause_concept} -> {law.effect_concept}")
        return law.law_id
    
    def get_law(self, law_id: str) -> Optional[CausalLaw]:
        """Retrieve a causal law by ID."""
        return self.laws.get(law_id)
    
    def get_laws_by_cause(self, cause_concept: str) -> List[CausalLaw]:
        """Get all laws where a concept is the cause."""
        law_ids = self.laws_by_cause.get(cause_concept, [])
        return [self.laws[law_id] for law_id in law_ids if law_id in self.laws]
    
    def get_laws_by_effect(self, effect_concept: str) -> List[CausalLaw]:
        """Get all laws where a concept is the effect."""
        law_ids = self.laws_by_effect.get(effect_concept, [])
        return [self.laws[law_id] for law_id in law_ids if law_id in self.laws]
    
    def get_all_laws(self) -> List[CausalLaw]:
        """Retrieve all causal laws."""
        return list(self.laws.values())
    
    def delete_law(self, law_id: str) -> bool:
        """Delete a causal law."""
        if law_id in self.laws:
            law = self.laws[law_id]
            del self.laws[law_id]
            
            # Remove from indexes
            if law.cause_concept in self.laws_by_cause:
                self.laws_by_cause[law.cause_concept].remove(law_id)
            if law.effect_concept in self.laws_by_effect:
                self.laws_by_effect[law.effect_concept].remove(law_id)
            
            self.logger.info(f"Deleted causal law {law_id}")
            return True
        return False


class KnowledgePhysicsEngine:
    """
    Discovers, validates, and models causal relationships within the knowledge base.
    
    The Knowledge Physics Engine goes beyond simple graph connections to understand
    underlying causal laws and relationships, enabling the system to predict outcomes
    and understand cause-and-effect dynamics.
    """
    
    def __init__(self, store: Optional[CausalLawStore] = None):
        """
        Initialize the Knowledge Physics Engine.
        
        Args:
            store: Optional custom causal law store
        """
        self.store = store or CausalLawStore()
        self.logger = logging.getLogger(__name__)
    
    def discover_causal_law(self, cause_concept: str, effect_concept: str, 
                           description: str = "", strength: float = 0.5) -> CausalLaw:
        """
        Discover and create a new causal law.
        
        Args:
            cause_concept: The concept that is the cause
            effect_concept: The concept that is the effect
            description: Description of the causal relationship
            strength: Initial strength of the causal relationship
            
        Returns:
            The created CausalLaw object
        """
        law = CausalLaw(
            cause_concept=cause_concept,
            effect_concept=effect_concept,
            description=description,
            strength=strength,
            confidence=strength  # Initial confidence equals strength
        )
        
        self.store.store_law(law)
        self.logger.info(f"Discovered causal law: {cause_concept} -> {effect_concept}")
        return law
    
    def get_law(self, law_id: str) -> Optional[CausalLaw]:
        """
        Retrieve a causal law by ID.
        
        Args:
            law_id: The ID of the causal law
            
        Returns:
            The CausalLaw object, or None if not found
        """
        return self.store.get_law(law_id)
    
    def get_effects(self, cause_concept: str) -> List[CausalLaw]:
        """
        Get all known effects of a cause.
        
        Args:
            cause_concept: The cause concept
            
        Returns:
            List of CausalLaw objects where the concept is the cause
        """
        return self.store.get_laws_by_cause(cause_concept)
    
    def get_causes(self, effect_concept: str) -> List[CausalLaw]:
        """
        Get all known causes of an effect.
        
        Args:
            effect_concept: The effect concept
            
        Returns:
            List of CausalLaw objects where the concept is the effect
        """
        return self.store.get_laws_by_effect(effect_concept)
    
    def predict_effects(self, cause_concept: str) -> List[Dict[str, Any]]:
        """
        Predict potential effects given a cause.
        
        Args:
            cause_concept: The cause concept
            
        Returns:
            List of predicted effects with confidence scores
        """
        laws = self.store.get_laws_by_cause(cause_concept)
        predictions = []
        
        for law in laws:
            prediction = {
                'effect': law.effect_concept,
                'confidence': law.confidence,
                'strength': law.strength,
                'law_id': law.law_id,
                'conditions': law.conditions,
                'exceptions': law.exceptions
            }
            predictions.append(prediction)
        
        # Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        return predictions
    
    def validate_causal_law(self, law_id: str, evidence: Dict[str, Any]) -> bool:
        """
        Validate a causal law with new evidence.
        
        Args:
            law_id: The ID of the causal law
            evidence: Evidence supporting the causal law
            
        Returns:
            True if validation was successful, False otherwise
        """
        law = self.store.get_law(law_id)
        if not law:
            return False
        
        law.add_evidence(evidence)
        law.validate()
        
        # Increase confidence based on evidence
        evidence_weight = evidence.get('weight', 0.1)
        law.confidence = min(1.0, law.confidence + evidence_weight * 0.1)
        
        self.logger.info(f"Validated causal law {law_id} with evidence")
        return True
    
    def add_condition_to_law(self, law_id: str, condition: str) -> bool:
        """
        Add a condition to a causal law.
        
        Args:
            law_id: The ID of the causal law
            condition: The condition to add
            
        Returns:
            True if successful, False otherwise
        """
        law = self.store.get_law(law_id)
        if not law:
            return False
        
        if condition not in law.conditions:
            law.conditions.append(condition)
        
        return True
    
    def add_exception_to_law(self, law_id: str, exception: str) -> bool:
        """
        Add an exception to a causal law.
        
        Args:
            law_id: The ID of the causal law
            exception: The exception to add
            
        Returns:
            True if successful, False otherwise
        """
        law = self.store.get_law(law_id)
        if not law:
            return False
        
        if exception not in law.exceptions:
            law.exceptions.append(exception)
        
        return True
    
    def trace_causal_chain(self, start_concept: str, max_depth: int = 5) -> List[List[Dict[str, Any]]]:
        """
        Trace causal chains starting from a concept.
        
        Args:
            start_concept: The starting concept
            max_depth: Maximum depth to trace
            
        Returns:
            List of causal chains
        """
        chains = []
        visited = set()
        
        def trace_chain(current: str, chain: List[Dict[str, Any]], depth: int) -> None:
            if depth > max_depth or current in visited:
                if chain:
                    chains.append(chain)
                return
            
            visited.add(current)
            effects = self.get_effects(current)
            
            if not effects:
                if chain:
                    chains.append(chain)
                return
            
            for law in effects:
                new_chain = chain + [{
                    'concept': law.effect_concept,
                    'confidence': law.confidence,
                    'law_id': law.law_id
                }]
                trace_chain(law.effect_concept, new_chain, depth + 1)
        
        trace_chain(start_concept, [], 1)
        return chains
    
    def find_causal_paths(self, start_concept: str, end_concept: str, max_depth: int = 5) -> List[List[str]]:
        """
        Find causal paths between two concepts.
        
        Args:
            start_concept: The starting concept
            end_concept: The target concept
            max_depth: Maximum depth to search
            
        Returns:
            List of causal paths from start to end
        """
        paths = []
        
        def dfs(current: str, target: str, path: List[str], visited: set, depth: int) -> None:
            if depth > max_depth:
                return
            
            if current == target:
                paths.append(path)
                return
            
            visited.add(current)
            effects = self.get_effects(current)
            
            for law in effects:
                if law.effect_concept not in visited:
                    dfs(law.effect_concept, target, path + [law.effect_concept], visited.copy(), depth + 1)
        
        dfs(start_concept, end_concept, [start_concept], set(), 1)
        return paths
    
    def get_causal_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about discovered causal laws.
        
        Returns:
            Dictionary containing causal law statistics
        """
        all_laws = self.store.get_all_laws()
        
        stats = {
            'total_laws': len(all_laws),
            'average_confidence': 0.0,
            'average_strength': 0.0,
            'average_validation_count': 0,
            'total_evidence': 0,
            'laws_by_strength': {}
        }
        
        if not all_laws:
            return stats
        
        confidences = [law.confidence for law in all_laws]
        strengths = [law.strength for law in all_laws]
        validation_counts = [law.validation_count for law in all_laws]
        
        stats['average_confidence'] = sum(confidences) / len(confidences)
        stats['average_strength'] = sum(strengths) / len(strengths)
        stats['average_validation_count'] = sum(validation_counts) / len(validation_counts)
        stats['total_evidence'] = sum(len(law.evidence) for law in all_laws)
        
        # Categorize by strength
        for strength_enum in CausalStrength:
            threshold = strength_enum.value
            count = sum(1 for law in all_laws if law.strength >= threshold)
            stats['laws_by_strength'][strength_enum.name] = count
        
        return stats
    
    def export_causal_laws(self, law_ids: Optional[List[str]] = None) -> str:
        """
        Export causal laws as JSON.
        
        Args:
            law_ids: Optional list of specific law IDs to export
            
        Returns:
            JSON string containing the causal laws
        """
        if law_ids:
            laws = [self.store.get_law(law_id) for law_id in law_ids if self.store.get_law(law_id)]
        else:
            laws = self.store.get_all_laws()
        
        return json.dumps([law.to_dict() for law in laws], indent=2, default=str)
