"""
Hajeen Brain v3 — العقل المدبّر الموحّد لمنصة Hajeen AI
=========================================================
الطبقة العليا التي تحوّل المنصة من wrapper للنماذج إلى عقل رقمي مستقل.

لا يصل أي طلب مباشرةً إلى أي نموذج. كل شيء يمر عبر HajeenBrain أولاً.

المصدرون الرسميون:
- HajeenBrainV3 — العقل المركزي الوحيد
- BrainRequest / BrainResponse — هياكل البيانات
- get_brain / get_brain_v3 — Singleton accessor
- UnifiedPromptBuilder — بناء الـ Prompts الوحيد
"""

from .brain_v3 import HajeenBrainV3, BrainRequest, BrainResponse, get_brain, get_brain_v3

# Compatibility aliases — V2 is deprecated, يشير لـ V3
HajeenBrain = HajeenBrainV3

__all__ = [
    "HajeenBrain",
    "HajeenBrainV3",
    "BrainRequest",
    "BrainResponse",
    "get_brain",
    "get_brain_v3",
]
