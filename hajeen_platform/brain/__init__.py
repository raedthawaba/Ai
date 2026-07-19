"""
Hajeen Brain v3 — العقل المدبّر لمنصة Hajeen AI
================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.

ملاحظة: هذا هو الإصدار الرسمي v3 مع Cognitive Layer متقدم.
"""

import asyncio

# Use v3 as the official version
_brain_instance = None


async def get_brain():
    """Get or create singleton HajeenBrainV3 instance (Official v3)."""
    global _brain_instance
    if _brain_instance is None:
        from .brain_v3 import HajeenBrainV3
        _brain_instance = HajeenBrainV3()
        # Call initialize if it exists
        if hasattr(_brain_instance, 'initialize') and callable(_brain_instance.initialize):
            await _brain_instance.initialize()
    return _brain_instance


# Keep v2 for backward compatibility
_brain_v2_instance = None


async def get_brain_v2():
    """Get or create singleton HajeenBrain v2 instance (Legacy)."""
    global _brain_v2_instance
    if _brain_v2_instance is None:
        from .brain import HajeenBrain
        _brain_v2_instance = HajeenBrain()
        # Call initialize if it exists
        if hasattr(_brain_v2_instance, 'initialize') and callable(_brain_v2_instance.initialize):
            await _brain_v2_instance.initialize()
    return _brain_v2_instance


# Alias for get_brain_v3
get_brain_v3 = get_brain


# Re-export classes for convenience
from .brain_v3 import HajeenBrainV3 as HajeenBrain, RequestType, ExecutionTrace
from .brain import BrainResponse  # Keep v2 response structure

# Re-export Knowledge modules
from .knowledge import (
    KnowledgeGraph, KGNode, KGEdge, NodeCategory, 
    RelationType, get_knowledge_graph
)

# Re-export Memory modules
from .memory import (
    MemoryFabric, MemoryEntry, SessionMemory, ConversationMemory,
    LongTermMemory, SemanticMemory, EpisodicMemory, ProceduralMemory,
    AgentMemory, get_memory_fabric
)

# Re-export Goal Manager
from .goal_manager import Goal, IntentType, ComplexityLevel

# Re-export Decision Engine (v3 if available)
try:
    from .decision_engine_v3 import DecisionEngine, get_decision_engine
except ImportError:
    from .decision_engine import DecisionEngine, get_decision_engine

# Re-export Model Router (v3 if available)
try:
    from .model_router_v3 import ModelRouter, get_model_router
except ImportError:
    from .model_router import ModelRouter, get_model_router

# Re-export Expert Models Layer
try:
    from .model_router_experts import (
        ExpertRegistry, ExpertConsultant, ModelSociety,
        get_expert_registry, get_expert_consultant, get_model_society,
        ExpertDomain, ExpertLevel, ExpertProfile, ExpertOpinion
    )
except ImportError:
    pass  # Expert layer not available

# Re-export Self Reflection
from .reflection.self_reflection import SelfReflection, get_self_reflection

# Re-export Cognitive Layer
try:
    from .cognitive_layer import (
        MetaBrain, WorldModel, ConceptEngine, CognitiveDNA,
        KnowledgePhysicsEngine, EvidenceCourt, HypothesisEngine,
        ReasoningEngine, CuriosityEngine, ExperienceMemory,
        DreamEngine, CognitiveConstitution, CognitiveEvolutionProtocol,
        CognitiveVersionControl, CognitiveCompiler, CognitiveEventSystem,
        ExperimentEngine, ModelSociety as CognitiveModelSociety
    )
except ImportError:
    pass  # Cognitive layer not fully available

__all__ = [
    # Core (v3 is official)
    "HajeenBrain",
    "BrainResponse",
    "get_brain",
    "RequestType",
    "ExecutionTrace",

    # Legacy (v2)
    "get_brain_v2",

    # Knowledge
    "KnowledgeGraph",
    "KGNode",
    "KGEdge",
    "NodeCategory",
    "RelationType",
    "get_knowledge_graph",

    # Memory
    "MemoryFabric",
    "MemoryEntry",
    "SessionMemory",
    "ConversationMemory",
    "LongTermMemory",
    "SemanticMemory",
    "EpisodicMemory",
    "ProceduralMemory",
    "AgentMemory",
    "get_memory_fabric",

    # Goal Management
    "Goal",
    "IntentType",
    "ComplexityLevel",

    # Decision
    "DecisionEngine",
    "get_decision_engine",

    # Routing
    "ModelRouter",
    "get_model_router",

    # Expert Models
    "ExpertRegistry",
    "ExpertConsultant",
    "ModelSociety",
    "get_expert_registry",
    "get_expert_consultant",
    "get_model_society",

    # Reflection
    "SelfReflection",
    "get_self_reflection",

    # Cognitive Layer
    "MetaBrain",
    "WorldModel",
    "ConceptEngine",
    "CognitiveDNA",
    "KnowledgePhysicsEngine",
    "EvidenceCourt",
    "HypothesisEngine",
    "ReasoningEngine",
    "CuriosityEngine",
    "ExperienceMemory",
    "DreamEngine",
    "CognitiveConstitution",
    "CognitiveEvolutionProtocol",
    "CognitiveVersionControl",
    "CognitiveCompiler",
    "CognitiveEventSystem",
    "ExperimentEngine",
]
