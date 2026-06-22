"""Embedding Cache Layer — Phase 6.5.

طبقة تخزين مؤقت للـ embeddings تجنّباً لإعادة الحساب.

تدعم:
  - In-memory cache (LRU)
  - SQLite-backed cache للاستمرارية
  - TTL (time-to-live) اختياري
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHE_DB_PATH = Path("storage_data/metadata/embedding_cache.db")


# ─────────────────────────────────────────────────────────────────────────────
# Cache Key
# ─────────────────────────────────────────────────────────────────────────────

def make_cache_key(text: str, model_name: str) -> str:
    """مفتاح فريد للـ cache بناءً على النص والنموذج."""
    payload = f"{model_name}::{text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory LRU Cache
# ─────────────────────────────────────────────────────────────────────────────

class LRUEmbeddingCache:
    """In-memory LRU cache للـ embeddings.

    Parameters
    ----------
    max_size:
        الحد الأقصى لعدد الـ embeddings في الذاكرة.
    ttl_seconds:
        مدة الصلاحية بالثواني (0 = لا تنتهي).
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[List[float]]:
        """استرجاع vector من الـ cache."""
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        if self._ttl > 0:
            age = time.time() - entry["timestamp"]
            if age > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None

        # LRU: نقل للنهاية
        self._cache.move_to_end(key)
        self._hits += 1
        return entry["vector"]

    def set(self, key: str, vector: List[float], metadata: Optional[Dict] = None) -> None:
        """تخزين vector في الـ cache."""
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = {
            "vector": vector,
            "timestamp": time.time(),
            "metadata": metadata or {},
        }
        # إزالة الأقدم إذا تجاوز الحجم
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def has(self, key: str) -> bool:
        return key in self._cache

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def stats(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SQLite-backed Persistent Cache
# ─────────────────────────────────────────────────────────────────────────────

class SQLiteEmbeddingCache:
    """Cache دائم للـ embeddings في SQLite.

    يُستخدم لتخزين الـ embeddings بعد الحساب وإعادة استخدامها
    دون الحاجة لإعادة الاستعلام من الـ API.
    """

    def __init__(self, db_path: Path = _CACHE_DB_PATH, ttl_seconds: int = 0) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._ttl = ttl_seconds
        self._init_schema()
        self._hits = 0
        self._misses = 0

    def _init_schema(self) -> None:
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                cache_key   TEXT PRIMARY KEY,
                source_id   TEXT NOT NULL,
                model_name  TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                dimensions  INTEGER NOT NULL,
                token_count INTEGER DEFAULT 0,
                created_at  REAL NOT NULL,
                accessed_at REAL NOT NULL
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_model ON embedding_cache(model_name)"
        )
        self._db.commit()

    def get(self, cache_key: str) -> Optional[List[float]]:
        """استرجاع vector من SQLite."""
        row = self._db.execute(
            "SELECT vector_json, created_at FROM embedding_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()

        if not row:
            self._misses += 1
            return None

        vector_json, created_at = row

        # فحص TTL
        if self._ttl > 0 and (time.time() - created_at) > self._ttl:
            self._db.execute(
                "DELETE FROM embedding_cache WHERE cache_key=?", (cache_key,)
            )
            self._db.commit()
            self._misses += 1
            return None

        # تحديث وقت الوصول
        self._db.execute(
            "UPDATE embedding_cache SET accessed_at=? WHERE cache_key=?",
            (time.time(), cache_key),
        )
        self._db.commit()
        self._hits += 1
        return json.loads(vector_json)

    def set(
        self,
        cache_key: str,
        vector: List[float],
        source_id: str = "",
        model_name: str = "",
        token_count: int = 0,
    ) -> None:
        """تخزين vector في SQLite."""
        now = time.time()
        self._db.execute("""
            INSERT OR REPLACE INTO embedding_cache
              (cache_key, source_id, model_name, vector_json, dimensions, token_count, created_at, accessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cache_key,
            source_id,
            model_name,
            json.dumps(vector),
            len(vector),
            token_count,
            now,
            now,
        ))
        self._db.commit()

    def has(self, cache_key: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM embedding_cache WHERE cache_key=?", (cache_key,)
        ).fetchone()
        return row is not None

    def count(self) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM embedding_cache"
        ).fetchone()[0]

    def evict_expired(self) -> int:
        """حذف الـ entries المنتهية الصلاحية."""
        if self._ttl <= 0:
            return 0
        cutoff = time.time() - self._ttl
        cur = self._db.execute(
            "DELETE FROM embedding_cache WHERE created_at < ?", (cutoff,)
        )
        self._db.commit()
        return cur.rowcount

    def clear(self) -> None:
        self._db.execute("DELETE FROM embedding_cache")
        self._db.commit()

    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "count": self.count(),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# EmbeddingCache — الواجهة الموحّدة
# ─────────────────────────────────────────────────────────────────────────────

class EmbeddingCache:
    """طبقة cache موحّدة: in-memory + SQLite.

    تُفحص الذاكرة أولاً، ثم SQLite، ثم تُحسب من المصدر.
    """

    def __init__(
        self,
        memory_max_size: int = 1000,
        persistent: bool = True,
        db_path: Path = _CACHE_DB_PATH,
        ttl_seconds: int = 0,
    ) -> None:
        self._memory = LRUEmbeddingCache(memory_max_size, ttl_seconds)
        self._sqlite: Optional[SQLiteEmbeddingCache] = None
        if persistent:
            try:
                self._sqlite = SQLiteEmbeddingCache(db_path, ttl_seconds)
            except Exception as exc:
                logger.warning("EmbeddingCache: فشل SQLite — %s", exc)

    def get(self, text: str, model_name: str) -> Optional[List[float]]:
        """استرجاع vector من الـ cache (memory ثم SQLite)."""
        key = make_cache_key(text, model_name)

        # 1. In-memory
        vector = self._memory.get(key)
        if vector is not None:
            return vector

        # 2. SQLite
        if self._sqlite:
            vector = self._sqlite.get(key)
            if vector is not None:
                # إعادة للذاكرة للاستخدام اللاحق
                self._memory.set(key, vector)
                return vector

        return None

    def set(
        self,
        text: str,
        model_name: str,
        vector: List[float],
        source_id: str = "",
        token_count: int = 0,
    ) -> None:
        """تخزين vector في الطبقتين."""
        key = make_cache_key(text, model_name)
        self._memory.set(key, vector)
        if self._sqlite:
            self._sqlite.set(key, vector, source_id, model_name, token_count)

    def has(self, text: str, model_name: str) -> bool:
        key = make_cache_key(text, model_name)
        return self._memory.has(key) or (
            self._sqlite.has(key) if self._sqlite else False
        )

    def stats(self) -> Dict[str, Any]:
        result = {"memory": self._memory.stats()}
        if self._sqlite:
            result["sqlite"] = self._sqlite.stats()
        return result

    def clear(self) -> None:
        self._memory.clear()
        if self._sqlite:
            self._sqlite.clear()
