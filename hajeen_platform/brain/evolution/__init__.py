"""
brain/evolution/ — Compatibility shim for SelfEvolution
========================================================
All evolution logic now lives in brain/reflection/self_evolution.py
This module re-exports from there for backward compatibility.

DEPRECATED: Use brain.reflection.self_evolution directly.
"""

from __future__ import annotations

import warnings

# Re-export everything from the unified implementation
from brain.reflection.self_evolution import (
    EvolutionProposal,
    EvolutionStatus,
    EvolutionTarget,
    SelfEvolution,
    get_self_evolution,
)

# Backward compatibility aliases
get_self_evolution_engine = get_self_evolution

__all__ = [
    "EvolutionProposal",
    "EvolutionStatus", 
    "EvolutionTarget",
    "SelfEvolution",
    "get_self_evolution",
    "get_self_evolution_engine",  # legacy alias
]

warnings.warn(
    "brain.evolution is deprecated. Use brain.reflection directly.",
    DeprecationWarning,
    stacklevel=2,
)
