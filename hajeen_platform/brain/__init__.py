"""
Hajeen Brain — العقل المدبّر لمنصة Hajeen AI
================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.

Official Entry Point: HajeenBrain (hajeen_brain.py)
"""

from .hajeen_brain import HajeenBrain, get_hajeen_brain

__all__ = ["HajeenBrain", "get_hajeen_brain"]
