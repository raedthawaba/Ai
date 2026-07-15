"""
Memory Fabric — نظام الذاكرة الموحّد
=======================================
يجمع جميع أنواع الذاكرة في واجهة واحدة متكاملة.

أنواع الذاكرة:
- Session Memory: ذاكرة الجلسة الحالية
- Conversation Memory: سجل المحادثات
- Long Memory: ذاكرة طويلة الأمد (Key-Value)
- Semantic Memory: ذاكرة دلالية (Vector-based)
- Episodic Memory: ذاكرة الأحداث المهمة
- Procedural Memory: ذاكرة كيفية تنفيذ المهام
- Agent Memory: ذاكرة خاصة بكل وكيل
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    entry_id: str
    memory_type: str
    content: str
    metadata: Dict[str, Any]
    relevance_score: float
    created_at: float
    accessed_at: float
    access_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "memory_type": self.memory_type,
            "content": self.content,
            "metadata": self.metadata,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at,
            "access_count": self.access_count,
        }


class SessionMemory:
    """ذاكرة الجلسة — تُمسح عند انتهاء الجلسة."""

    def __init__(self, session_id: str, max_entries: int = 100) -> None:
        self.session_id = session_id
        self._store: List[Dict] = []
        self._max = max_entries

    def add(self, key: str, value: Any) -> None:
        self._store.append({"key": key, "value": value, "at": time.time()})
        if len(self._store) > self._max:
            self._store = self._store[-self._max:]

    def get(self, key: str) -> Optional[Any]:
        for entry in reversed(self._store):
            if entry["key"] == key:
                return entry["value"]
        return None

    def get_all(self) -> List[Dict]:
        return list(self._store)

    def clear(self) -> None:
        self._store.clear()


class ConversationMemory:
    """ذاكرة المحادثة — سجل الرسائل."""

    def __init__(self, session_id: str, window_size: int = 20) -> None:
        self.session_id = session_id
        self._messages: List[Dict] = []
        self._window = window_size

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        self._messages.append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "at": time.time(),
        })

    def get_window(self) -> List[Dict[str, str]]:
        """آخر N رسالة للسياق."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self._messages[-self._window:]
        ]

    def get_summary_context(self) -> str:
        """ملخص نصي للمحادثة."""
        lines = []
        for m in self._messages[-10:]:
            lines.append(f"{m['role'].upper()}: {m['content'][:200]}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._messages.clear()


class LongTermMemory:
    """ذاكرة طويلة الأمد — مستمرة عبر الجلسات (Key-Value + JSON)."""

    def __init__(self, storage_path: str = "storage_data/brain/long_memory") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Any] = {}

    def _key_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(" ", "_")
        return self._path / f"{safe}.json"

    def store(self, key: str, value: Any, metadata: Optional[Dict] = None) -> None:
        data = {
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "stored_at": time.time(),
        }
        self._cache[key] = data
        try:
            with open(self._key_path(key), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("long_term_memory: write error: %s", e)

    def recall(self, key: str) -> Optional[Any]:
        if key in self._cache:
            return self._cache[key]["value"]
        path = self._key_path(key)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._cache[key] = data
                return data["value"]
            except Exception as e:
                logger.error("long_term_memory: read error: %s", e)
        return None

    def list_keys(self) -> List[str]:
        return [p.stem.replace("_", " ") for p in self._path.glob("*.json")]


class SemanticMemory:
    """ذاكرة دلالية — تخزين وبحث بناءً على المعنى."""

    def __init__(self) -> None:
        self._entries: List[MemoryEntry] = []

    def store(self, content: str, metadata: Optional[Dict] = None, relevance: float = 0.8) -> str:
        entry = MemoryEntry(
            entry_id=str(uuid.uuid4()),
            memory_type="semantic",
            content=content,
            metadata=metadata or {},
            relevance_score=relevance,
            created_at=time.time(),
            accessed_at=time.time(),
        )
        self._entries.append(entry)
        return entry.entry_id

    def search(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        """بحث بسيط بالكلمات المفتاحية (يمكن تطويره لاستخدام Embeddings)."""
        query_words = set(query.lower().split())
        scored = []
        for entry in self._entries:
            content_words = set(entry.content.lower().split())
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), 1)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:top_k]]
        for e in results:
            e.access_count += 1
            e.accessed_at = time.time()
        return results


class EpisodicMemory:
    """ذاكرة الأحداث — تخزين لحظات مهمة في تاريخ النظام."""

    def __init__(self) -> None:
        self._episodes: List[Dict] = []

    def record(self, event_type: str, description: str, outcome: str, metadata: Optional[Dict] = None) -> None:
        self._episodes.append({
            "episode_id": str(uuid.uuid4()),
            "event_type": event_type,
            "description": description,
            "outcome": outcome,
            "metadata": metadata or {},
            "recorded_at": time.time(),
        })

    def get_similar_episodes(self, event_type: str, limit: int = 5) -> List[Dict]:
        return [e for e in self._episodes if e["event_type"] == event_type][-limit:]

    def get_recent(self, limit: int = 10) -> List[Dict]:
        return self._episodes[-limit:]


class ProceduralMemory:
    """ذاكرة الإجراءات — كيفية تنفيذ المهام (خطوات قابلة للاسترجاع)."""

    def __init__(self) -> None:
        self._procedures: Dict[str, Dict] = {}

    def learn_procedure(self, name: str, steps: List[str], metadata: Optional[Dict] = None) -> None:
        self._procedures[name] = {
            "name": name,
            "steps": steps,
            "metadata": metadata or {},
            "learned_at": time.time(),
            "usage_count": 0,
        }
        logger.info("procedural_memory: learned procedure '%s' (%d steps)", name, len(steps))

    def recall_procedure(self, name: str) -> Optional[List[str]]:
        if name in self._procedures:
            self._procedures[name]["usage_count"] += 1
            return self._procedures[name]["steps"]
        # بحث بالتشابه
        for pname, proc in self._procedures.items():
            if name.lower() in pname.lower() or pname.lower() in name.lower():
                proc["usage_count"] += 1
                return proc["steps"]
        return None

    def list_procedures(self) -> List[str]:
        return list(self._procedures.keys())


class AgentMemory:
    """ذاكرة خاصة بكل وكيل — تتبع حالة الوكلاء وتجاربهم."""

    def __init__(self) -> None:
        self._agents: Dict[str, Dict] = {}

    def get_or_create(self, agent_id: str) -> Dict:
        if agent_id not in self._agents:
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "experiences": [],
                "preferences": {},
                "stats": {"tasks": 0, "success": 0, "failures": 0},
                "created_at": time.time(),
            }
        return self._agents[agent_id]

    def record_experience(self, agent_id: str, task: str, outcome: str, success: bool) -> None:
        agent = self.get_or_create(agent_id)
        agent["experiences"].append({
            "task": task,
            "outcome": outcome,
            "success": success,
            "at": time.time(),
        })
        agent["stats"]["tasks"] += 1
        agent["stats"]["success" if success else "failures"] += 1
        # احتفظ بآخر 100 تجربة
        if len(agent["experiences"]) > 100:
            agent["experiences"] = agent["experiences"][-100:]

    def get_agent_stats(self, agent_id: str) -> Dict:
        return self._agents.get(agent_id, {}).get("stats", {})


class MemoryFabric:
    """
    نظام الذاكرة الموحّد — يجمع كل أنواع الذاكرة في واجهة واحدة.
    """

    def __init__(self, storage_base: str = "storage_data/brain") -> None:
        self._sessions: Dict[str, SessionMemory] = {}
        self._conversations: Dict[str, ConversationMemory] = {}
        self._long_term = LongTermMemory(f"{storage_base}/long_memory")
        self._semantic = SemanticMemory()
        self._episodic = EpisodicMemory()
        self._procedural = ProceduralMemory()
        self._agent = AgentMemory()

        # تسجيل إجراءات افتراضية
        self._load_default_procedures()

    def _load_default_procedures(self) -> None:
        self._procedural.learn_procedure("train_model", [
            "جمع البيانات وفحصها",
            "تنظيف البيانات",
            "تحليل الجودة",
            "إعداد dataset",
            "تدريب النموذج",
            "تقييم الأداء",
            "نشر النموذج",
        ])
        self._procedural.learn_procedure("answer_question", [
            "تحليل السؤال",
            "البحث في الذاكرة",
            "اختيار النموذج المناسب",
            "توليد الإجابة",
            "التحقق من الجودة",
        ])

    # ── Session Memory ─────────────────────────────────────────────────────
    def get_session(self, session_id: str) -> SessionMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemory(session_id)
        return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].clear()
        if session_id in self._conversations:
            self._conversations[session_id].clear()

    # ── Conversation Memory ────────────────────────────────────────────────
    def get_conversation(self, session_id: str) -> ConversationMemory:
        if session_id not in self._conversations:
            self._conversations[session_id] = ConversationMemory(session_id)
        return self._conversations[session_id]

    # ── Long-Term Memory ───────────────────────────────────────────────────
    def remember(self, key: str, value: Any, metadata: Optional[Dict] = None) -> None:
        self._long_term.store(key, value, metadata)

    def recall(self, key: str) -> Optional[Any]:
        return self._long_term.recall(key)

    # ── Semantic Memory ────────────────────────────────────────────────────
    def memorize_semantically(self, content: str, metadata: Optional[Dict] = None) -> str:
        return self._semantic.store(content, metadata)

    def search_semantic(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        return self._semantic.search(query, top_k)

    # ── Episodic Memory ────────────────────────────────────────────────────
    def record_episode(self, event_type: str, description: str, outcome: str) -> None:
        self._episodic.record(event_type, description, outcome)

    def recall_episodes(self, event_type: str) -> List[Dict]:
        return self._episodic.get_similar_episodes(event_type)

    # ── Procedural Memory ─────────────────────────────────────────────────
    def learn_how(self, name: str, steps: List[str]) -> None:
        self._procedural.learn_procedure(name, steps)

    def recall_how(self, name: str) -> Optional[List[str]]:
        return self._procedural.recall_procedure(name)

    # ── Agent Memory ───────────────────────────────────────────────────────
    def record_agent_experience(
        self, agent_id: str, task: str, outcome: str, success: bool
    ) -> None:
        self._agent.record_experience(agent_id, task, outcome, success)

    def get_agent_stats(self, agent_id: str) -> Dict:
        return self._agent.get_agent_stats(agent_id)

    # ── Overview ───────────────────────────────────────────────────────────
    def get_overview(self) -> Dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "active_conversations": len(self._conversations),
            "long_term_keys": len(self._long_term.list_keys()),
            "semantic_entries": len(self._semantic._entries),
            "episodes": len(self._episodic._episodes),
            "procedures": len(self._procedural._procedures),
            "tracked_agents": len(self._agent._agents),
        }


# Singleton
_fabric: Optional[MemoryFabric] = None


def get_memory_fabric() -> MemoryFabric:
    global _fabric
    if _fabric is None:
        _fabric = MemoryFabric()
    return _fabric
