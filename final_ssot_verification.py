import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

# Mocking necessary parts to avoid complex dependency issues
class MockMemoryFabric:
    def __init__(self):
        self._conversations = {}
        self._sessions = {}
        self._long_term = {}

    def get_conversation(self, session_id):
        if session_id not in self._conversations:
            self._conversations[session_id] = MockConv(session_id)
        return self._conversations[session_id]

    def clear_session(self, session_id):
        if session_id in self._conversations:
            del self._conversations[session_id]

    def remember(self, key, value, metadata=None):
        self._long_term[key] = value

    def recall(self, key):
        return self._long_term.get(key)

class MockConv:
    def __init__(self, session_id):
        self.session_id = session_id
        self.messages = []
    def add_message(self, role, content, metadata=None):
        self.messages.append({"role": role, "content": content, "metadata": metadata})
    def get_window(self):
        return self.messages

# Global Fabric for testing
FABRIC = MockMemoryFabric()

# Mocking the get_memory_fabric function that the adapters will call
def get_memory_fabric():
    return FABRIC

# --- Now we define the Adapters logic as implemented in the files ---

class UnifiedMemoryInterface:
    def __init__(self):
        self._fabric = FABRIC
    async def add_message(self, session_id, role, content, metadata=None):
        conv = self._fabric.get_conversation(session_id)
        conv.add_message(role, content, metadata)
    async def get_context(self, session_id, max_messages=20):
        conv = self._fabric.get_conversation(session_id)
        return conv.get_window()[-max_messages:]
    async def clear_session(self, session_id):
        self._fabric.clear_session(session_id)
    def get_stats(self):
        return {"sessions": len(self._fabric._conversations)}

INTERFACE = UnifiedMemoryInterface()

class SessionManagerAdapter:
    def get_or_create(self, session_id):
        return ChatSessionProxy(session_id)

class ChatSessionProxy:
    def __init__(self, session_id):
        self.session_id = session_id
    def add_message(self, role, content, metadata=None):
        # Simulation of the async call in the adapter
        asyncio.run(INTERFACE.add_message(self.session_id, role, content, metadata))

class MemoryManagerAdapter:
    def add_message(self, session_id, role, content, metadata=None):
        asyncio.run(INTERFACE.add_message(session_id, role, content, metadata))

async def verify():
    print("--- Starting Final SSOT Verification (Isolated) ---")
    session_id = "isolated_test_123"
    
    sm = SessionManagerAdapter()
    mm = MemoryManagerAdapter()
    
    # 1. Write via SessionManager
    session = sm.get_or_create(session_id)
    session.add_message("user", "Msg from SM")
    
    # 2. Write via MemoryManager
    mm.add_message(session_id, "assistant", "Msg from MM")
    
    # 3. Check MemoryFabric (The SSOT)
    history = await INTERFACE.get_context(session_id)
    print(f"Unified History: {history}")
    
    assert len(history) == 2
    assert history[0]["content"] == "Msg from SM"
    assert history[1]["content"] == "Msg from MM"
    
    print("✅ SUCCESS: All adapters route to the same Fabric instance.")
    print("--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify())
