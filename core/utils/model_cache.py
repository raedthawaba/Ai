from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CacheEntry:
    __slots__ = ("model_id", "path", "size_bytes", "created_at", "last_used")

    def __init__(self, model_id: str, path: Path, size_bytes: int) -> None:
        self.model_id = model_id
        self.path = path
        self.size_bytes = size_bytes
        self.created_at = time.time()
        self.last_used = time.time()

    def touch(self) -> None:
        self.last_used = time.time()


class ModelCache:
    """Disk-based cache for downloaded models with LRU eviction."""

    def __init__(
        self,
        cache_dir: str = "storage_data/model_cache",
        max_size_gb: float = 50.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = int(max_size_gb * 1024 ** 3)
        self._entries: Dict[str, CacheEntry] = {}
        self._scan_existing()

    def _scan_existing(self) -> None:
        for p in self.cache_dir.iterdir():
            if p.is_dir():
                size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                self._entries[p.name] = CacheEntry(p.name, p, size)
        logger.info("ModelCache scanned %d cached models", len(self._entries))

    def get_path(self, model_id: str) -> Optional[Path]:
        safe_id = self._safe_name(model_id)
        entry = self._entries.get(safe_id)
        if entry and entry.path.exists():
            entry.touch()
            return entry.path
        return None

    def put(self, model_id: str, source_dir: Path) -> Path:
        safe_id = self._safe_name(model_id)
        dest = self.cache_dir / safe_id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(str(source_dir), str(dest))
        size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
        self._entries[safe_id] = CacheEntry(model_id, dest, size)
        self._evict_if_needed()
        return dest

    def is_cached(self, model_id: str) -> bool:
        safe_id = self._safe_name(model_id)
        return safe_id in self._entries and self._entries[safe_id].path.exists()

    def remove(self, model_id: str) -> bool:
        safe_id = self._safe_name(model_id)
        entry = self._entries.pop(safe_id, None)
        if entry and entry.path.exists():
            shutil.rmtree(entry.path)
            return True
        return False

    def total_size_gb(self) -> float:
        return sum(e.size_bytes for e in self._entries.values()) / 1024 ** 3

    def list_cached(self) -> List[Dict]:
        return [
            {
                "model_id": e.model_id,
                "size_gb": round(e.size_bytes / 1024 ** 3, 2),
                "last_used": e.last_used,
            }
            for e in sorted(self._entries.values(), key=lambda x: x.last_used, reverse=True)
        ]

    def _evict_if_needed(self) -> None:
        total = sum(e.size_bytes for e in self._entries.values())
        if total <= self.max_size_bytes:
            return
        sorted_entries = sorted(self._entries.values(), key=lambda x: x.last_used)
        for entry in sorted_entries:
            if total <= self.max_size_bytes:
                break
            total -= entry.size_bytes
            self.remove(entry.model_id)
            logger.info("LRU evicted: %s", entry.model_id)

    @staticmethod
    def _safe_name(model_id: str) -> str:
        return model_id.replace("/", "__").replace(":", "_")
