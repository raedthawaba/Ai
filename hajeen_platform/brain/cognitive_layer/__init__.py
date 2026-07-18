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

from .intent_analyzer import (
    IntentAnalyzer,
    Intent,
    IntentCategory,
    get_intent_analyzer,
)

from .context_analyzer import (
    ContextAnalyzer,
    ContextAnalysis,
    get_context_analyzer,
)

from .reasoning_engine import (
    ReasoningEngine,
    ReasoningResult,
    ReasoningStrategy,
    get_reasoning_engine,
)

from .cognitive_compiler import (
    CognitiveCompiler,
    CognitiveEvent,
    EventType,
    FactExtractor,
    ConceptExtractor,
    RelationshipDiscoverer,
    EvidenceValidator
)

from .cognitive_event_system import (
    CognitiveEventSystem,
    CognitiveEventStore
)

from .concept_engine import (
    ConceptEngine,
    Concept,
    ConceptStore
)

from .cognitive_dna import (
    CognitiveDNA,
    CognitiveDNAManager,
    CognitiveDNAStore
)

from .knowledge_physics_engine import (
    KnowledgePhysicsEngine,
    CausalLaw,
    CausalLawStore,
    CausalStrength
)

from .evidence_court import (
    EvidenceCourt,
    EvidenceItem,
    ValidationReport,
    SourceType,
    EvidenceQuality
)

from .hypothesis_engine import (
    HypothesisEngine,
    Hypothesis,
    HypothesisStatus
)

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
    "ReasoningStrategy",
    "get_reasoning_engine",
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
    "HypothesisStatus"
]
