"""
Hajeen Brain v3 — العقل المدبّر الموحّد لمنصة Hajeen AI
=========================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.
"""

from .brain_v3 import HajeenBrainV3, BrainRequest, BrainResponse, get_brain

# Compatibility aliases — V2 is deprecated
HajeenBrain = HajeenBrainV3

__all__ = ["HajeenBrain", "HajeenBrainV3", "BrainRequest", "BrainResponse", "get_brain"]
