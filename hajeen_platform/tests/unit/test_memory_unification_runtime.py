import asyncio
import os
import shutil
import sys

# إضافة المسار للجذور المطلوبة
sys.path.append("/home/ubuntu/Ai")
sys.path.append("/home/ubuntu/Ai/hajeen_platform")

from hajeen_platform.brain.memory.unified_interface import get_unified_memory
from hajeen_platform.services.memory.session_manager import get_session_manager
from hajeen_platform.core.memory.memory_manager import MemoryManager

async def test_memory_unification_ssot():
    """
    اختبار التحقق من توحيد الذاكرة:
    1. التأكد من أن الكتابة عبر أي مكون تصل إلى MemoryFabric.
    2. التأكد من عدم وجود ملفات جديدة تنشأ في المجلدات القديمة.
    """
    session_id = "test_unification_session"
    unified_memory = get_unified_memory()
    await unified_memory.initialize()
    
    # مسح أي بيانات سابقة
    await unified_memory.clear_session(session_id)
    
    # 1. اختبار SessionManager (Adapter)
    sm = get_session_manager()
    session = sm.get_or_create(session_id)
    session.add_message("user", "Hello from SessionManager Adapter")
    
    # ننتظر قليلاً لمعالجة الـ async task
    await asyncio.sleep(0.1)
    
    # التحقق من وصول الرسالة لـ MemoryFabric عبر الواجهة الموحدة
    history = await unified_memory.get_context(session_id)
    assert len(history) > 0
    assert history[-1]["content"] == "Hello from SessionManager Adapter"
    
    # 2. اختبار MemoryManager (Adapter)
    mm = MemoryManager()
    mm.add_message(session_id, "assistant", "Hello from MemoryManager Adapter")
    
    await asyncio.sleep(0.1)
    
    history = await unified_memory.get_context(session_id)
    assert len(history) >= 2
    assert history[-1]["content"] == "Hello from MemoryManager Adapter"
    
    # 3. التحقق من عدم وجود كتابة في storage_data/conversations (المجلد القديم)
    legacy_path = "storage_data/conversations"
    if os.path.exists(legacy_path):
        # التأكد من أن الملف الخاص بالجلسة لم يتم تحديثه أو إنشاؤه
        session_file = os.path.join(legacy_path, f"{session_id}.json")
        assert not os.path.exists(session_file), "Legacy storage should NOT be used!"

    print("\n✅ Verification Passed: All components route to MemoryFabric via UnifiedMemoryInterface.")

if __name__ == "__main__":
    asyncio.run(test_memory_unification_ssot())
