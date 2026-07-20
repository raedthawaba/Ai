"""Brain Reflection Package — التفكير الذاتي والتطور."""
from .self_evolution import EvolutionProposal, SelfEvolution, get_self_evolution
from .self_reflection import ReflectionReport, SelfReflection, get_self_reflection

__all__ = [
    "SelfReflection", "ReflectionReport", "get_self_reflection",
    "SelfEvolution", "EvolutionProposal", "get_self_evolution",
]
