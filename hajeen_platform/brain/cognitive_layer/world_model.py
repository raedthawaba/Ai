"""
World Model - Internal representation of the world and its dynamics.

The World Model maintains an internal representation of the world, including
entities, relationships, and dynamics, enabling the system to reason about
and predict world states.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorldEntity:
    """
    Represents an entity in the world model.
    """
    entity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    entity_type: str = ""
    
    # Properties
    properties: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    # State
    current_state: Dict[str, Any] = field(default_factory=dict)
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # Relationships
    relationships: Dict[str, List[str]] = field(default_factory=dict)  # rel_type -> [entity_ids]
    
    # Dynamics
    change_rate: float = 0.0
    stability: float = 0.5
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_updated'] = self.last_updated.isoformat()
        return data


@dataclass
class WorldDynamics:
    """
    Represents the dynamics and rules governing the world.
    """
    dynamics_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Rules
    physical_laws: List[str] = field(default_factory=list)
    causal_rules: List[str] = field(default_factory=list)
    behavioral_rules: List[str] = field(default_factory=list)
    
    # Constraints
    constraints: List[str] = field(default_factory=list)
    
    # Time
    time_step: float = 1.0  # seconds
    simulation_speed: float = 1.0
    
    # State
    current_world_state: Dict[str, Any] = field(default_factory=dict)
    predicted_states: List[Dict[str, Any]] = field(default_factory=list)
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_updated'] = self.last_updated.isoformat()
        return data


class WorldModel:
    """
    Maintains an internal representation of the world and its dynamics.
    
    The World Model enables the system to reason about the world, predict
    future states, and plan actions based on its understanding of world dynamics.
    """
    
    def __init__(self):
        """Initialize the World Model."""
        self.entities: Dict[str, WorldEntity] = {}
        self.entities_by_type: Dict[str, List[str]] = {}  # type -> [entity_ids]
        self.dynamics: Optional[WorldDynamics] = None
        self.logger = logging.getLogger(__name__)
    
    def initialize_world_dynamics(self) -> WorldDynamics:
        """
        Initialize world dynamics.
        
        Returns:
            The initialized WorldDynamics
        """
        self.dynamics = WorldDynamics()
        self.logger.info("Initialized world dynamics")
        return self.dynamics
    
    def add_entity(self, name: str, entity_type: str, properties: Optional[Dict[str, Any]] = None) -> WorldEntity:
        """
        Add an entity to the world model.
        
        Args:
            name: Name of the entity
            entity_type: Type of the entity
            properties: Optional properties of the entity
            
        Returns:
            The added WorldEntity
        """
        entity = WorldEntity(
            name=name,
            entity_type=entity_type,
            properties=properties or {}
        )
        
        self.entities[entity.entity_id] = entity
        
        # Index by type
        if entity_type not in self.entities_by_type:
            self.entities_by_type[entity_type] = []
        self.entities_by_type[entity_type].append(entity.entity_id)
        
        self.logger.info(f"Added entity {name} of type {entity_type}")
        return entity
    
    def get_entity(self, entity_id: str) -> Optional[WorldEntity]:
        """
        Retrieve an entity by ID.
        
        Args:
            entity_id: The ID of the entity
            
        Returns:
            The WorldEntity, or None if not found
        """
        return self.entities.get(entity_id)
    
    def get_entities_by_type(self, entity_type: str) -> List[WorldEntity]:
        """
        Get all entities of a specific type.
        
        Args:
            entity_type: The type of entities
            
        Returns:
            List of WorldEntity objects
        """
        entity_ids = self.entities_by_type.get(entity_type, [])
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]
    
    def update_entity_state(self, entity_id: str, new_state: Dict[str, Any]) -> bool:
        """
        Update the state of an entity.
        
        Args:
            entity_id: The ID of the entity
            new_state: The new state
            
        Returns:
            True if successful, False otherwise
        """
        entity = self.entities.get(entity_id)
        if not entity:
            return False
        
        # Store old state in history
        entity.state_history.append(entity.current_state.copy())
        
        # Update current state
        entity.current_state = new_state
        entity.last_updated = datetime.utcnow()
        
        return True
    
    def add_relationship(self, entity_id_1: str, entity_id_2: str, relationship_type: str) -> bool:
        """
        Add a relationship between two entities.
        
        Args:
            entity_id_1: ID of the first entity
            entity_id_2: ID of the second entity
            relationship_type: Type of relationship
            
        Returns:
            True if successful, False otherwise
        """
        entity1 = self.entities.get(entity_id_1)
        entity2 = self.entities.get(entity_id_2)
        
        if not entity1 or not entity2:
            return False
        
        # Add relationship from entity1 to entity2
        if relationship_type not in entity1.relationships:
            entity1.relationships[relationship_type] = []
        if entity_id_2 not in entity1.relationships[relationship_type]:
            entity1.relationships[relationship_type].append(entity_id_2)
        
        return True
    
    def add_physical_law(self, law: str) -> bool:
        """
        Add a physical law to the world dynamics.
        
        Args:
            law: Description of the physical law
            
        Returns:
            True if successful, False otherwise
        """
        if not self.dynamics:
            self.initialize_world_dynamics()
        
        if law not in self.dynamics.physical_laws:
            self.dynamics.physical_laws.append(law)
        
        return True
    
    def add_causal_rule(self, rule: str) -> bool:
        """
        Add a causal rule to the world dynamics.
        
        Args:
            rule: Description of the causal rule
            
        Returns:
            True if successful, False otherwise
        """
        if not self.dynamics:
            self.initialize_world_dynamics()
        
        if rule not in self.dynamics.causal_rules:
            self.dynamics.causal_rules.append(rule)
        
        return True
    
    def add_behavioral_rule(self, rule: str) -> bool:
        """
        Add a behavioral rule to the world dynamics.
        
        Args:
            rule: Description of the behavioral rule
            
        Returns:
            True if successful, False otherwise
        """
        if not self.dynamics:
            self.initialize_world_dynamics()
        
        if rule not in self.dynamics.behavioral_rules:
            self.dynamics.behavioral_rules.append(rule)
        
        return True
    
    def add_constraint(self, constraint: str) -> bool:
        """
        Add a constraint to the world dynamics.
        
        Args:
            constraint: Description of the constraint
            
        Returns:
            True if successful, False otherwise
        """
        if not self.dynamics:
            self.initialize_world_dynamics()
        
        if constraint not in self.dynamics.constraints:
            self.dynamics.constraints.append(constraint)
        
        return True
    
    def predict_world_state(self, steps: int = 1) -> List[Dict[str, Any]]:
        """
        Predict future world states.
        
        Args:
            steps: Number of steps to predict
            
        Returns:
            List of predicted world states
        """
        if not self.dynamics:
            return []
        
        predictions = []
        
        for step in range(steps):
            predicted_state = {
                'step': step + 1,
                'timestamp': datetime.utcnow().isoformat(),
                'entities': {},
                'dynamics': {
                    'physical_laws': len(self.dynamics.physical_laws),
                    'causal_rules': len(self.dynamics.causal_rules),
                    'behavioral_rules': len(self.dynamics.behavioral_rules)
                }
            }
            
            # Simulate state prediction
            for entity in self.entities.values():
                predicted_state['entities'][entity.entity_id] = {
                    'name': entity.name,
                    'type': entity.entity_type,
                    'state': entity.current_state
                }
            
            predictions.append(predicted_state)
        
        self.dynamics.predicted_states = predictions
        return predictions
    
    def simulate_action(self, entity_id: str, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Simulate the effect of an action on the world.
        
        Args:
            entity_id: ID of the entity performing the action
            action: The action to simulate
            parameters: Optional action parameters
            
        Returns:
            Simulation result
        """
        entity = self.entities.get(entity_id)
        if not entity:
            return {'success': False, 'error': 'Entity not found'}
        
        # Simulate action effect
        result = {
            'entity_id': entity_id,
            'action': action,
            'parameters': parameters or {},
            'success': True,
            'effects': {
                'entity_state_change': 'Simulated state change',
                'world_state_change': 'Simulated world state change',
                'side_effects': []
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return result
    
    def get_world_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the world model.
        
        Returns:
            Dictionary containing world statistics
        """
        stats = {
            'total_entities': len(self.entities),
            'entities_by_type': {},
            'total_relationships': 0,
            'total_laws': 0,
            'total_constraints': 0
        }
        
        # Count by type
        for entity_type in self.entities_by_type:
            stats['entities_by_type'][entity_type] = len(self.entities_by_type[entity_type])
        
        # Count relationships
        for entity in self.entities.values():
            for rel_type, entities in entity.relationships.items():
                stats['total_relationships'] += len(entities)
        
        # Count dynamics
        if self.dynamics:
            stats['total_laws'] = (
                len(self.dynamics.physical_laws) +
                len(self.dynamics.causal_rules) +
                len(self.dynamics.behavioral_rules)
            )
            stats['total_constraints'] = len(self.dynamics.constraints)
        
        return stats
    
    def export_world_model(self) -> str:
        """
        Export the world model as JSON.
        
        Returns:
            JSON string containing the world model
        """
        model_data = {
            'entities': [e.to_dict() for e in self.entities.values()],
            'dynamics': self.dynamics.to_dict() if self.dynamics else None
        }
        
        return json.dumps(model_data, indent=2, default=str)
