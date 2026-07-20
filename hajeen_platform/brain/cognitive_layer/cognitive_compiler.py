"""
Cognitive Compiler - Central processing unit for knowledge transformation.

The Cognitive Compiler is responsible for transforming raw input into structured
cognitive events and knowledge updates. It acts as the central hub through which
all information flows before entering the system's knowledge base.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Enumeration of cognitive event types."""
    FACT_EXTRACTION = "fact_extraction"
    CONCEPT_EXTRACTION = "concept_extraction"
    RELATIONSHIP_DISCOVERY = "relationship_discovery"
    EVIDENCE_VALIDATION = "evidence_validation"
    KNOWLEDGE_UPDATE = "knowledge_update"
    EXPERIENCE_LEARNING = "experience_learning"
    REASONING_PROCESS = "reasoning_process"
    DECISION_MAKING = "decision_making"


@dataclass
class CognitiveEvent:
    """
    Represents a structured cognitive event with full context and processing details.
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: EventType = EventType.FACT_EXTRACTION
    
    # Input and Context
    raw_input: str = ""
    goal: Optional[str] = None
    intent: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Processing Details
    knowledge_used: List[str] = field(default_factory=list)
    models_consulted: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    
    # Reasoning and Hypotheses
    thinking_steps: List[str] = field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    
    # Evidence and Results
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    
    # Error and Evaluation
    errors: List[str] = field(default_factory=list)
    success_failure_reasons: Optional[str] = None
    confidence_level: float = 0.5
    
    # Learning
    lessons_learned: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['event_type'] = self.event_type.value
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class FactExtractor:
    """Extracts factual statements from raw input."""
    
    def extract(self, raw_input: str) -> List[Dict[str, Any]]:
        """
        Extract facts from raw input.
        
        Args:
            raw_input: The raw text input
            
        Returns:
            List of extracted facts with metadata
        """
        facts = []
        
        # Simple fact extraction logic (to be enhanced with NLP)
        sentences = raw_input.split('.')
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                fact = {
                    'text': sentence,
                    'type': self._classify_fact(sentence),
                    'confidence': 0.7,
                    'extracted_at': datetime.utcnow().isoformat()
                }
                facts.append(fact)
        
        logger.info(f"Extracted {len(facts)} facts from input")
        return facts
    
    def _classify_fact(self, sentence: str) -> str:
        """Classify the type of fact."""
        if any(word in sentence.lower() for word in ['is', 'are', 'was', 'were']):
            return 'state'
        elif any(word in sentence.lower() for word in ['cause', 'lead', 'result']):
            return 'causal'
        else:
            return 'general'


class ConceptExtractor:
    """Extracts key concepts and entities from raw input."""
    
    def extract(self, raw_input: str) -> List[Dict[str, Any]]:
        """
        Extract concepts from raw input.
        
        Args:
            raw_input: The raw text input
            
        Returns:
            List of extracted concepts with metadata
        """
        concepts = []
        
        # Simple concept extraction logic (to be enhanced with NLP/NER)
        words = raw_input.split()
        
        # Filter for potential concepts (capitalized words, nouns, etc.)
        for word in words:
            if word and word[0].isupper() and len(word) > 2:
                concept = {
                    'name': word.strip('.,;:!?'),
                    'type': 'entity',
                    'confidence': 0.6,
                    'extracted_at': datetime.utcnow().isoformat()
                }
                if concept not in concepts:  # Avoid duplicates
                    concepts.append(concept)
        
        logger.info(f"Extracted {len(concepts)} concepts from input")
        return concepts


class RelationshipDiscoverer:
    """Discovers relationships between facts and concepts."""
    
    def discover(self, facts: List[Dict[str, Any]], concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Discover relationships between facts and concepts.
        
        Args:
            facts: List of extracted facts
            concepts: List of extracted concepts
            
        Returns:
            List of discovered relationships
        """
        relationships = []
        
        # Simple relationship discovery (to be enhanced with semantic analysis)
        for fact in facts:
            for concept in concepts:
                if concept['name'].lower() in fact['text'].lower():
                    relationship = {
                        'source': concept['name'],
                        'target': fact['text'],
                        'type': 'mentioned_in',
                        'confidence': 0.5,
                        'discovered_at': datetime.utcnow().isoformat()
                    }
                    relationships.append(relationship)
        
        logger.info(f"Discovered {len(relationships)} relationships")
        return relationships


class EvidenceValidator:
    """Validates evidence and assigns confidence scores."""
    
    def validate(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate evidence and assign confidence scores.
        
        Args:
            evidence: List of evidence items
            
        Returns:
            Validation report with confidence scores
        """
        validation_report = {
            'total_evidence': len(evidence),
            'valid_evidence': 0,
            'invalid_evidence': 0,
            'average_confidence': 0.0,
            'details': []
        }
        
        total_confidence = 0.0
        
        for item in evidence:
            # Simple validation logic
            confidence = self._calculate_confidence(item)
            
            detail = {
                'evidence': item,
                'confidence': confidence,
                'is_valid': confidence > 0.5,
                'validated_at': datetime.utcnow().isoformat()
            }
            validation_report['details'].append(detail)
            
            if confidence > 0.5:
                validation_report['valid_evidence'] += 1
            else:
                validation_report['invalid_evidence'] += 1
            
            total_confidence += confidence
        
        if len(evidence) > 0:
            validation_report['average_confidence'] = total_confidence / len(evidence)
        
        logger.info(f"Validated {len(evidence)} evidence items")
        return validation_report
    
    def _calculate_confidence(self, item: Dict[str, Any]) -> float:
        """Calculate confidence score for an evidence item."""
        # Simple confidence calculation (to be enhanced)
        base_confidence = item.get('confidence', 0.5)
        return min(base_confidence * 1.1, 1.0)  # Slight boost


class CognitiveCompiler:
    """
    Central processing unit for cognitive event creation and knowledge transformation.
    
    The Cognitive Compiler orchestrates the entire pipeline of transforming raw input
    into structured cognitive events and validated knowledge updates.
    """
    
    def __init__(self):
        """Initialize the Cognitive Compiler with its sub-components."""
        self.fact_extractor = FactExtractor()
        self.concept_extractor = ConceptExtractor()
        self.relationship_discoverer = RelationshipDiscoverer()
        self.evidence_validator = EvidenceValidator()
        self.logger = logging.getLogger(__name__)
    
    def compile_input(self, raw_input: str, context: Optional[Dict[str, Any]] = None) -> CognitiveEvent:
        """
        Compile raw input into a structured cognitive event.
        
        This is the main entry point for the Cognitive Compiler. It orchestrates
        the entire processing pipeline.
        
        Args:
            raw_input: The raw text input to process
            context: Optional context information
            
        Returns:
            A structured CognitiveEvent
        """
        self.logger.info(f"Starting cognitive compilation for input: {raw_input[:100]}...")
        
        # Create the cognitive event
        event = CognitiveEvent(
            event_type=EventType.FACT_EXTRACTION,
            raw_input=raw_input,
            context=context or {}
        )
        
        try:
            # Step 1: Extract facts
            facts = self.extract_facts(raw_input)
            event.results['facts'] = facts
            
            # Step 2: Extract concepts
            concepts = self.extract_concepts(raw_input)
            event.results['concepts'] = concepts
            
            # Step 3: Discover relationships
            relationships = self.discover_relationships(facts, concepts)
            event.results['relationships'] = relationships
            
            # Step 4: Validate evidence
            validation_report = self.validate_evidence(facts)
            event.results['validation'] = validation_report
            
            # Update confidence based on validation
            if validation_report['average_confidence'] > 0:
                event.confidence_level = validation_report['average_confidence']
            
            event.success_failure_reasons = "Successfully compiled cognitive event"
            self.logger.info(f"Cognitive compilation completed with confidence: {event.confidence_level}")
            
        except Exception as e:
            event.errors.append(str(e))
            event.success_failure_reasons = f"Error during compilation: {str(e)}"
            self.logger.error(f"Error during cognitive compilation: {str(e)}")
        
        return event
    
    def extract_facts(self, raw_input: str) -> List[Dict[str, Any]]:
        """Extract facts from raw input."""
        return self.fact_extractor.extract(raw_input)
    
    def extract_concepts(self, raw_input: str) -> List[Dict[str, Any]]:
        """Extract concepts from raw input."""
        return self.concept_extractor.extract(raw_input)
    
    def discover_relationships(self, facts: List[Dict[str, Any]], concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Discover relationships between facts and concepts."""
        return self.relationship_discoverer.discover(facts, concepts)
    
    def validate_evidence(self, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate evidence and assign confidence scores."""
        return self.evidence_validator.validate(evidence)
    
    def update_knowledge_graph(self, event: CognitiveEvent) -> bool:
        """
        Update the knowledge graph based on the cognitive event.
        
        Args:
            event: The cognitive event containing processed information
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            # This will be integrated with Brain V3's KnowledgeGraph
            self.logger.info(f"Updating knowledge graph from event {event.event_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating knowledge graph: {str(e)}")
            return False
    
    def store_experience(self, event: CognitiveEvent) -> bool:
        """
        Store the cognitive event as an experience.
        
        Args:
            event: The cognitive event to store
            
        Returns:
            True if storage was successful, False otherwise
        """
        try:
            self.logger.info(f"Storing cognitive event {event.event_id} as experience")
            return True
        except Exception as e:
            self.logger.error(f"Error storing experience: {str(e)}")
            return False
