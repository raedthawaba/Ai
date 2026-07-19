"""
Hajeen Brain v2 — العقل المدبّر لمنصة Hajeen AI
================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.

ملاحظة: brain_v3 متاح أيضاً مع Cognitive Layer متقدم.
"""

import asyncio

_brain_instance = None


async def get_brain():
    """Get or create singleton HajeenBrain instance."""
    global _brain_instance
    if _brain_instance is None:
        from .brain import HajeenBrain
        _brain_instance = HajeenBrain()
        # Call initialize if it exists
        if hasattr(_brain_instance, 'initialize') and callable(_brain_instance.initialize):
            await _brain_instance.initialize()
    return _brain_instance


# brain_v3 with Cognitive Layer integration
_brain_v3_instance = None


async def get_brain_v3():
    """Get or create singleton HajeenBrainV3 instance."""
    global _brain_v3_instance
    if _brain_v3_instance is None:
        from .brain_v3 import HajeenBrainV3
        _brain_v3_instance = HajeenBrainV3()
        # Call initialize if it exists
        if hasattr(_brain_v3_instance, 'initialize') and callable(_brain_v3_instance.initialize):
            await _brain_v3_instance.initialize()
    return _brain_v3_instance


# Re-export classes for convenience
from .brain import BrainRequest, BrainResponse
from .brain_v3 import RequestType, ExecutionTrace

__all__ = [
    "HajeenBrain",
    "BrainRequest",
    "BrainResponse",
    "get_brain",
    "HajeenBrainV3",
    "RequestType",
    "ExecutionTrace",
    "get_brain_v3",
]
