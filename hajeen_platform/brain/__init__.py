"""
Hajeen Brain v2 — العقل المدبّر لمنصة Hajeen AI
================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.
"""

from .brain import HajeenBrain, get_brain

__all__ = ["HajeenBrain", "get_brain"]
