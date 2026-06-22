from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LongTermMemory:
    """Persistent key-value memory backed by JSON files on disk.

    Each session gets its own file under *storage_dir*.
    In production this would be replaced with a vector DB or PostgreSQL.
    """

    def __init__(self, storage_dir: str = "storage_data/long_term_memory") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("..", "")
        return self.storage_dir / f"{safe}.json"

    def save(self, session_id: str, key: str, value: Any) -> None:
        data = self._load_raw(session_id)
        data[key] = {"value": value, "saved_at": time.time()}
        self._write(session_id, data)

    def load(self, session_id: str, key: str, default: Any = None) -> Any:
        data = self._load_raw(session_id)
        entry = data.get(key)
        if entry is None:
            return default
        return entry.get("value", default)

    def delete(self, session_id: str, key: str) -> bool:
        data = self._load_raw(session_id)
        if key in data:
            del data[key]
            self._write(session_id, data)
            return True
        return False

    def list_keys(self, session_id: str) -> List[str]:
        return list(self._load_raw(session_id).keys())

    def get_all(self, session_id: str) -> Dict[str, Any]:
        raw = self._load_raw(session_id)
        return {k: v["value"] for k, v in raw.items()}

    def clear_session(self, session_id: str) -> None:
        p = self._path(session_id)
        if p.exists():
            p.unlink()

    def _load_raw(self, session_id: str) -> Dict:
        p = self._path(session_id)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read long-term memory for %s: %s", session_id, exc)
            return {}

    def _write(self, session_id: str, data: Dict) -> None:
        p = self._path(session_id)
        try:
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to write long-term memory for %s: %s", session_id, exc)
