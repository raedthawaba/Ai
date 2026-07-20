"""
Cognitive Layer — طبقة الإدراك المتقدمة
======================================

تتكون من:
1. Intent Analyzer — محلّل النية
2. Goal Analyzer — محلّل الأهداف
3. Context Analyzer — محلّل السياق
4. Reasoning Engine — محرك الاستدلال
5. Planner — المخطط الديناميكي

جميع المكونات تستخدم الاستدلال العميق وليس مطابقة الكلمات المفتاحية.
"""

from .cognitive_compiler import (
    CognitiveCompiler,
    CognitiveEvent,
    ConceptExtractor,
    EventType,
    EvidenceValidator,
    FactExtractor,
    RelationshipDiscoverer,
)
from .cognitive_constitution import (
    CognitiveConstitution,
    ConstitutionalViolation,
    GovernanceRule,
    Principle,
    PrincipleCategory,
)
from .cognitive_dna import CognitiveDNA, CognitiveDNAManager, CognitiveDNAStore
from .cognitive_event_system import CognitiveEventStore, CognitiveEventSystem
from .cognitive_evolution_protocol import (
    CognitiveEvolutionProtocol,
    EvolutionGoal,
    EvolutionIteration,
    EvolutionPhase,
    ImprovementType,
)
from .cognitive_version_control import (
    CognitiveVersionControl,
    SystemVersion,
    VersionCheckpoint,
)
from .concept_engine import Concept, ConceptEngine, ConceptStore
from .context_analyzer import (
    ContextAnalysis,
    ContextAnalyzer,
    get_context_analyzer,
)
from .curiosity_engine import (
    CuriosityEngine,
    CuriosityQuery,
    GapPriority,
    GapType,
    KnowledgeGap,
)
from .dream_engine import Dream, DreamEngine, DreamStatus, DreamType
from .evidence_court import (
    EvidenceCourt,
    EvidenceItem,
    EvidenceQuality,
    SourceType,
    ValidationReport,
)
from .experience_memory import (
    Experience,
    ExperienceMemory,
    ExperienceType,
    LearnedLesson,
)
from .experiment_engine import (
    Experiment,
    ExperimentDesign,
    ExperimentEngine,
    ExperimentStatus,
    ExperimentType,
)
from .hypothesis_engine import Hypothesis, HypothesisEngine, HypothesisStatus
from .intent_analyzer import (
    Intent,
    IntentAnalyzer,
    IntentCategory,
    get_intent_analyzer,
)
from .knowledge_physics_engine import (
    CausalLaw,
    CausalLawStore,
    CausalStrength,
    KnowledgePhysicsEngine,
)
from .meta_brain import CognitiveMetric, MetaBrain, SelfReflection
from .model_society import ExpertiseLevel, ExpertModel, ModelInteraction, ModelSociety
from .reasoning_engine import (
    LLMCallError,
    ReasoningEngine,
    ReasoningEngineError,
    ReasoningResult,
    ReasoningStep,
    ReasoningStrategy,
    RiskAssessment,
    SolutionOption,
    ValidationError,
    create_reasoning_engine,
    get_reasoning_engine,
    reset_reasoning_engine,
)
from .world_model import WorldDynamics, WorldEntity, WorldModel

__all__ = [
    "IntentAnalyzer",
    "Intent",
    "IntentCategory",
    "get_intent_analyzer",
    "ContextAnalyzer",
    "ContextAnalysis",
    "get_context_analyzer",
    "ReasoningEngine",
    "ReasoningResult",
    "ReasoningStep",
    "RiskAssessment",
    "SolutionOption",
    "ReasoningStrategy",
    "ReasoningEngineError",
    "LLMCallError",
    "ValidationError",
    "get_reasoning_engine",
    "reset_reasoning_engine",
    "create_reasoning_engine",
    "CognitiveCompiler",
    "CognitiveEvent",
    "EventType",
    "FactExtractor",
    "ConceptExtractor",
    "RelationshipDiscoverer",
    "EvidenceValidator",
    "CognitiveEventSystem",
    "CognitiveEventStore",
    "ConceptEngine",
    "Concept",
    "ConceptStore",
    "CognitiveDNA",
    "CognitiveDNAManager",
    "CognitiveDNAStore",
    "KnowledgePhysicsEngine",
    "CausalLaw",
    "CausalLawStore",
    "CausalStrength",
    "EvidenceCourt",
    "EvidenceItem",
    "ValidationReport",
    "SourceType",
    "EvidenceQuality",
    "HypothesisEngine",
    "Hypothesis",
    "HypothesisStatus",
    "ModelSociety",
    "ExpertModel",
    "ModelInteraction",
    "ExpertiseLevel",
    "ExperimentEngine",
    "Experiment",
    "ExperimentDesign",
    "ExperimentStatus",
    "ExperimentType",
    "ExperienceMemory",
    "Experience",
    "LearnedLesson",
    "ExperienceType",
    "CuriosityEngine",
    "KnowledgeGap",
    "CuriosityQuery",
    "GapType",
    "GapPriority",
    "WorldModel",
    "WorldEntity",
    "WorldDynamics",
    "DreamEngine",
    "Dream",
    "DreamType",
    "DreamStatus",
    "MetaBrain",
    "CognitiveMetric",
    "SelfReflection",
    "CognitiveEvolutionProtocol",
    "EvolutionGoal",
    "EvolutionIteration",
    "EvolutionPhase",
    "ImprovementType",
    "CognitiveConstitution",
    "Principle",
    "GovernanceRule",
    "ConstitutionalViolation",
    "PrincipleCategory",
    "CognitiveVersionControl",
    "SystemVersion",
    "VersionCheckpoint"
]
