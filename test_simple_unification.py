import asyncio
import os
import sys

# إعداد المسارات
sys.path.append("/home/ubuntu/Ai")
sys.path.append("/home/ubuntu/Ai/hajeen_platform")

async def test_ssot():
    print("--- Starting SSOT Verification ---")
    
    from hajeen_platform.brain.memory.unified_interface import get_unified_memory
    from hajeen_platform.services.memory.session_manager import get_session_manager
    from hajeen_platform.core.memory.memory_manager import MemoryManager
    
    session_id = "final_ssot_test"
    unified = get_unified_memory()
    await unified.initialize()
    
    # 1. اختبار الكتابة عبر SessionManager
    sm = get_session_manager()
    session = sm.get_or_create(session_id)
    session.add_message("user", "SSOT Test Message 1")
    
    # 2. اختبار الكتابة عبر MemoryManager
    mm = MemoryManager()
    mm.add_message(session_id, "assistant", "SSOT Test Message 2")
    
    await asyncio.sleep(0.5)
    
    # 3. التحقق من أن كل شيء وصل لـ MemoryFabric
    history = await unified.get_context(session_id)
    print(f"History in MemoryFabric: {history}")
    
    assert any(m["content"] == "SSOT Test Message 1" for m in history)
    assert any(m["content"] == "SSOT Test Message 2" for m in history)
    
    # 4. التحقق من عدم وجود ملفات في المسار القديم
    legacy_dir = "storage_data/conversations"
    legacy_file = os.path.join(legacy_dir, f"{session_id}.json")
    if os.path.exists(legacy_file):
        print(f"❌ FAILURE: Legacy file found at {legacy_file}")
        sys.exit(1)
    else:
        print("✅ SUCCESS: No legacy files created.")

    print("--- SSOT Verification Passed ---")

if __name__ == "__main__":
    asyncio.run(test_ssot())
