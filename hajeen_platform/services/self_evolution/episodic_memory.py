from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Long-term episodic store that persists agent experiences (successes and
    failures) to disk as JSONL, with keyword-based retrieval and semantic
    search hooks ready for vector store integration.
    """

    def __init__(self, storage_path: str = "./agent_experiences.jsonl") -> None:
        self.storage_path = storage_path
        os.makedirs(os.path.dirname(os.path.abspath(storage_path)), exist_ok=True)
        self.experiences: List[Dict[str, Any]] = self._load_experiences()
        logger.info(
            "EpisodicMemory initialised — %d experiences loaded from %s",
            len(self.experiences),
            storage_path,
        )

    # ── Write ────────────────────────────────────────────────────────────

    def add_experience(
        self,
        prompt: str,
        actions: List[str],
        outcome: str,
        success: bool,
        reflection: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        experience = {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt,
            "actions": actions,
            "outcome": outcome,
            "success": success,
            "reflection": reflection,
            "metadata": metadata or {},
        }
        self.experiences.append(experience)
        self._append_to_disk(experience)
        logger.info(
            "Experience stored (success=%s). Total: %d", success, len(self.experiences)
        )

    # ── Read ─────────────────────────────────────────────────────────────

    def retrieve_experiences(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Keyword-based retrieval — returns most-recent matching experiences."""
        q = query.lower()
        matched = [
            exp
            for exp in self.experiences
            if q in exp["prompt"].lower() or q in exp["outcome"].lower()
        ]
        matched.sort(key=lambda x: x["timestamp"], reverse=True)
        return matched[:top_k]

    def get_successful_experiences(self, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        items = [e for e in self.experiences if e["success"]]
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items[:top_k] if top_k else items

    def get_failed_experiences(self, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        items = [e for e in self.experiences if not e["success"]]
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items[:top_k] if top_k else items

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        return list(reversed(self.experiences[-n:]))

    def summary(self) -> Dict[str, Any]:
        total = len(self.experiences)
        successes = sum(1 for e in self.experiences if e["success"])
        return {
            "total": total,
            "successes": successes,
            "failures": total - successes,
            "success_rate": round(successes / total, 3) if total else 0.0,
        }

    # ── Persistence ──────────────────────────────────────────────────────

    def _load_experiences(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.storage_path):
            return []
        loaded: List[Dict[str, Any]] = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Skipping corrupt experience record: %s", exc)
        return loaded

    def _append_to_disk(self, experience: Dict[str, Any]) -> None:
        """Append a single experience without rewriting the whole file."""
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(experience, ensure_ascii=False) + "\n")

    def rebuild_file(self) -> None:
        """Rewrite the entire file from in-memory list (use after bulk edits)."""
        with open(self.storage_path, "w", encoding="utf-8") as f:
            for exp in self.experiences:
                f.write(json.dumps(exp, ensure_ascii=False) + "\n")
        logger.debug("EpisodicMemory file rebuilt with %d records.", len(self.experiences))
