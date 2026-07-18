"""
Model Society - Management of expert models and their interactions.

The Model Society manages a collection of specialized expert models, each with
specific expertise domains, and coordinates their interactions for collaborative
problem-solving and knowledge synthesis.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ExpertiseLevel(Enum):
    """Enumeration of expertise levels."""
    NOVICE = 0.3
    INTERMEDIATE = 0.6
    EXPERT = 0.85
    MASTER = 0.95


@dataclass
class ExpertModel:
    """
    Represents an expert model with specific domain expertise.
    """
    model_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    domain: str = ""
    description: str = ""
    
    # Expertise
    expertise_level: float = 0.5
    specializations: List[str] = field(default_factory=list)
    
    # Capabilities
    capabilities: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    
    # Performance
    accuracy_score: float = 0.5
    reliability_score: float = 0.5
    response_time: float = 1.0  # seconds
    
    # Relationships
    collaborators: List[str] = field(default_factory=list)  # model_ids
    dependencies: List[str] = field(default_factory=list)  # model_ids
    
    # History
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    usage_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['last_used']:
            data['last_used'] = self.last_used.isoformat()
        return data


@dataclass
class ModelInteraction:
    """
    Records an interaction between models.
    """
    interaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    initiator_model: str = ""
    target_model: str = ""
    
    # Interaction Details
    interaction_type: str = "consultation"  # consultation, collaboration, validation
    query: str = ""
    response: str = ""
    
    # Results
    success: bool = False
    confidence: float = 0.5
    
    # Timeline
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration: float = 0.0  # seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class ModelSociety:
    """
    Manages a collection of expert models and coordinates their interactions.
    
    The Model Society enables collaborative problem-solving by managing multiple
    specialized expert models and facilitating their interactions.
    """
    
    def __init__(self):
        """Initialize the Model Society."""
        self.models: Dict[str, ExpertModel] = {}
        self.models_by_domain: Dict[str, List[str]] = {}  # domain -> [model_ids]
        self.interactions: Dict[str, ModelInteraction] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_model(self, name: str, domain: str, description: str = "",
                      expertise_level: float = 0.5) -> ExpertModel:
        """
        Register a new expert model.
        
        Args:
            name: Name of the model
            domain: Domain of expertise
            description: Description of the model
            expertise_level: Level of expertise (0.0 to 1.0)
            
        Returns:
            The registered ExpertModel
        """
        model = ExpertModel(
            name=name,
            domain=domain,
            description=description,
            expertise_level=expertise_level
        )
        
        self.models[model.model_id] = model
        
        # Index by domain
        if domain not in self.models_by_domain:
            self.models_by_domain[domain] = []
        self.models_by_domain[domain].append(model.model_id)
        
        self.logger.info(f"Registered expert model {name} in domain {domain}")
        return model
    
    def get_model(self, model_id: str) -> Optional[ExpertModel]:
        """
        Retrieve a model by ID.
        
        Args:
            model_id: The ID of the model
            
        Returns:
            The ExpertModel, or None if not found
        """
        return self.models.get(model_id)
    
    def get_models_by_domain(self, domain: str) -> List[ExpertModel]:
        """
        Get all models in a specific domain.
        
        Args:
            domain: The domain of expertise
            
        Returns:
            List of ExpertModel objects
        """
        model_ids = self.models_by_domain.get(domain, [])
        return [self.models[mid] for mid in model_ids if mid in self.models]
    
    def add_capability(self, model_id: str, capability: str) -> bool:
        """
        Add a capability to a model.
        
        Args:
            model_id: The ID of the model
            capability: The capability to add
            
        Returns:
            True if successful, False otherwise
        """
        model = self.models.get(model_id)
        if not model:
            return False
        
        if capability not in model.capabilities:
            model.capabilities.append(capability)
        
        return True
    
    def add_limitation(self, model_id: str, limitation: str) -> bool:
        """
        Add a limitation to a model.
        
        Args:
            model_id: The ID of the model
            limitation: The limitation to add
            
        Returns:
            True if successful, False otherwise
        """
        model = self.models.get(model_id)
        if not model:
            return False
        
        if limitation not in model.limitations:
            model.limitations.append(limitation)
        
        return True
    
    def add_specialization(self, model_id: str, specialization: str) -> bool:
        """
        Add a specialization to a model.
        
        Args:
            model_id: The ID of the model
            specialization: The specialization to add
            
        Returns:
            True if successful, False otherwise
        """
        model = self.models.get(model_id)
        if not model:
            return False
        
        if specialization not in model.specializations:
            model.specializations.append(specialization)
        
        return True
    
    def establish_collaboration(self, model_id_1: str, model_id_2: str) -> bool:
        """
        Establish a collaboration between two models.
        
        Args:
            model_id_1: ID of the first model
            model_id_2: ID of the second model
            
        Returns:
            True if successful, False otherwise
        """
        model1 = self.models.get(model_id_1)
        model2 = self.models.get(model_id_2)
        
        if not model1 or not model2:
            return False
        
        if model_id_2 not in model1.collaborators:
            model1.collaborators.append(model_id_2)
        if model_id_1 not in model2.collaborators:
            model2.collaborators.append(model_id_1)
        
        self.logger.info(f"Established collaboration between {model1.name} and {model2.name}")
        return True
    
    def add_dependency(self, model_id: str, dependency_id: str) -> bool:
        """
        Add a dependency relationship between models.
        
        Args:
            model_id: ID of the dependent model
            dependency_id: ID of the model it depends on
            
        Returns:
            True if successful, False otherwise
        """
        model = self.models.get(model_id)
        dependency = self.models.get(dependency_id)
        
        if not model or not dependency:
            return False
        
        if dependency_id not in model.dependencies:
            model.dependencies.append(dependency_id)
        
        return True
    
    def consult_model(self, model_id: str, query: str) -> Dict[str, Any]:
        """
        Consult a model for expertise.
        
        Args:
            model_id: The ID of the model to consult
            query: The query or problem to address
            
        Returns:
            Consultation result
        """
        model = self.models.get(model_id)
        if not model:
            return {'success': False, 'error': 'Model not found'}
        
        # Simulate model consultation
        response = {
            'model_id': model_id,
            'model_name': model.name,
            'query': query,
            'response': f"Expert analysis from {model.name} on {query}",
            'confidence': model.accuracy_score,
            'expertise_level': model.expertise_level
        }
        
        # Update model usage
        model.last_used = datetime.utcnow()
        model.usage_count += 1
        
        self.logger.info(f"Consulted model {model.name} with query: {query}")
        return response
    
    def collaborate_models(self, model_ids: List[str], problem: str) -> Dict[str, Any]:
        """
        Coordinate collaboration between multiple models.
        
        Args:
            model_ids: List of model IDs to collaborate
            problem: The problem to solve collaboratively
            
        Returns:
            Collaboration result
        """
        models = [self.models.get(mid) for mid in model_ids if mid in self.models]
        
        if not models:
            return {'success': False, 'error': 'No valid models provided'}
        
        # Simulate collaborative problem-solving
        result = {
            'collaboration_id': str(uuid.uuid4()),
            'models_involved': [m.name for m in models],
            'problem': problem,
            'solution': f"Collaborative solution from {len(models)} expert models",
            'confidence': sum(m.accuracy_score for m in models) / len(models),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Update model usage
        for model in models:
            model.last_used = datetime.utcnow()
            model.usage_count += 1
        
        self.logger.info(f"Coordinated collaboration of {len(models)} models for problem: {problem}")
        return result
    
    def validate_with_models(self, claim: str, model_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Validate a claim using multiple expert models.
        
        Args:
            claim: The claim to validate
            model_ids: Optional list of specific models to use (defaults to all)
            
        Returns:
            Validation result
        """
        if model_ids:
            models = [self.models.get(mid) for mid in model_ids if mid in self.models]
        else:
            models = list(self.models.values())
        
        if not models:
            return {'success': False, 'error': 'No models available'}
        
        # Simulate validation
        validation_scores = [m.reliability_score for m in models]
        average_score = sum(validation_scores) / len(validation_scores)
        
        result = {
            'claim': claim,
            'models_consulted': len(models),
            'validation_scores': validation_scores,
            'average_confidence': average_score,
            'is_valid': average_score > 0.6,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.logger.info(f"Validated claim with {len(models)} models, confidence: {average_score}")
        return result
    
    def record_interaction(self, initiator_id: str, target_id: str, 
                          interaction_type: str, query: str, response: str,
                          success: bool, confidence: float, duration: float) -> ModelInteraction:
        """
        Record an interaction between models.
        
        Args:
            initiator_id: ID of the initiating model
            target_id: ID of the target model
            interaction_type: Type of interaction
            query: The query
            response: The response
            success: Whether the interaction was successful
            confidence: Confidence in the response
            duration: Duration of the interaction
            
        Returns:
            The recorded ModelInteraction
        """
        interaction = ModelInteraction(
            initiator_model=initiator_id,
            target_model=target_id,
            interaction_type=interaction_type,
            query=query,
            response=response,
            success=success,
            confidence=confidence,
            duration=duration
        )
        
        self.interactions[interaction.interaction_id] = interaction
        return interaction
    
    def get_society_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the model society.
        
        Returns:
            Dictionary containing society statistics
        """
        stats = {
            'total_models': len(self.models),
            'domains_covered': len(self.models_by_domain),
            'average_expertise': 0.0,
            'average_accuracy': 0.0,
            'average_reliability': 0.0,
            'total_interactions': len(self.interactions),
            'total_usage': 0
        }
        
        if not self.models:
            return stats
        
        expertise_levels = [m.expertise_level for m in self.models.values()]
        accuracy_scores = [m.accuracy_score for m in self.models.values()]
        reliability_scores = [m.reliability_score for m in self.models.values()]
        
        stats['average_expertise'] = sum(expertise_levels) / len(expertise_levels)
        stats['average_accuracy'] = sum(accuracy_scores) / len(accuracy_scores)
        stats['average_reliability'] = sum(reliability_scores) / len(reliability_scores)
        stats['total_usage'] = sum(m.usage_count for m in self.models.values())
        
        return stats
    
    def export_models(self, model_ids: Optional[List[str]] = None) -> str:
        """
        Export models as JSON.
        
        Args:
            model_ids: Optional list of specific model IDs to export
            
        Returns:
            JSON string containing the models
        """
        if model_ids:
            models = [self.models[mid] for mid in model_ids if mid in self.models]
        else:
            models = list(self.models.values())
        
        return json.dumps([m.to_dict() for m in models], indent=2, default=str)
