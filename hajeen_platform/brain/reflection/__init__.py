"""Brain Reflection Package — التفكير الذاتي والتطور."""
from .self_reflection import SelfReflection, ReflectionReport, get_self_reflection
from .self_evolution import SelfEvolution, EvolutionProposal, get_self_evolution

__all__ = [
    "SelfReflection", "ReflectionReport", "get_self_reflection",
    "SelfEvolution", "EvolutionProposal", "get_self_evolution",
]
