"""Storage Manager — إدارة موحّدة لجميع طبقات التخزين.

هيكل مجلدات التخزين:
storage_data/
├── raw/           — البيانات الخام
├── bronze/        — بعد التنظيف الأولي
├── silver/        — بعد الإثراء
├── gold/          — البيانات المنسّقة النهائية
└── metadata/      — SQLite للفهرسة والبيانات الوصفية

يدعم:
- Singleton instance لمنع تعدد الاتصالات
- منع duplicate writes عبر content hash
- file locking عند الكتابة
- JSONL storage
- cleanup utilities
- metadata tracking
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .raw_store.local_storage import LocalRawStorage
from .processed_store.bronze_layer import BronzeLayer
from .processed_store.silver_layer import SilverLayer
from .processed_store.gold_layer import GoldLayer
from .metadata_store.sqlite_catalog import SQLiteCatalog
from .repositories.article_repository import ArticleRepository
from .repositories.channel_repository import ChannelRepository
from .repositories.pipeline_repository import PipelineRepository

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR = Path("storage_data")
_DEDUP_SET_MAX = 100_000


class StorageManager:
    """إدارة موحّدة لجميع أنظمة التخزين مع singleton support."""

    def __init__(self, base_data_dir: Union[str, Path] = _DEFAULT_BASE_DIR) -> None:
        self.base_data_dir = Path(base_data_dir).resolve()
        self.base_data_dir.mkdir(parents=True, exist_ok=True)

        self.raw_storage = LocalRawStorage(base_dir=self.base_data_dir / "raw")
        self.bronze_layer = BronzeLayer(base_dir=self.base_data_dir / "bronze")
        self.silver_layer = SilverLayer(base_dir=self.base_data_dir / "silver")
        self.gold_layer = GoldLayer(base_dir=self.base_data_dir / "gold")

        metadata_dir = self.base_data_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_catalog = SQLiteCatalog(db_path=metadata_dir / "catalog.db")
        self.article_repo = ArticleRepository(catalog=self.metadata_catalog)
        self.channel_repo = ChannelRepository(catalog=self.metadata_catalog)
        self.pipeline_repo = PipelineRepository(catalog=self.metadata_catalog)

        # Set in-memory للكشف عن duplicates
        self._seen_hashes: set[str] = set()
        self._dedup_lock = threading.Lock()

        self._connected = False
        logger.info("StorageManager: مجلد التخزين = %s", self.base_data_dir)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """الاتصال بجميع أنظمة التخزين."""
        if self._connected:
            return
        await self.raw_storage.connect()
        await self.bronze_layer.connect()
        await self.silver_layer.connect()
        await self.gold_layer.connect()
        await self.metadata_catalog.connect()
        self._connected = True
        logger.info("StorageManager: اتّصل بجميع أنظمة التخزين")

    async def disconnect(self) -> None:
        """قطع الاتصال بجميع أنظمة التخزين."""
        if not self._connected:
            return
        await self.raw_storage.disconnect()
        await self.bronze_layer.disconnect()
        await self.silver_layer.disconnect()
        await self.gold_layer.disconnect()
        await self.metadata_catalog.disconnect()
        self._connected = False

    async def health_check(self) -> Dict[str, Any]:
        """فحص صحة جميع أنظمة التخزين."""
        return {
            "connected": self._connected,
            "raw": await self.raw_storage.health_check(),
            "bronze": await self.bronze_layer.health_check(),
            "silver": await self.silver_layer.health_check(),
            "gold": await self.gold_layer.health_check(),
            "metadata": await self.metadata_catalog.health_check(),
            "dedup_cache_size": len(self._seen_hashes),
        }

    # ------------------------------------------------------------------
    # Deduplication helpers
    # ------------------------------------------------------------------

    def _compute_hash(self, data: Any) -> str:
        """حساب hash للبيانات للكشف عن التكرار."""
        if isinstance(data, dict):
            key = data.get("id") or json.dumps(data, sort_keys=True, ensure_ascii=False)
        elif isinstance(data, str):
            key = data
        else:
            key = str(data)
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def is_duplicate(self, data: Any) -> bool:
        """فحص إذا كانت البيانات مكررة."""
        h = self._compute_hash(data)
        with self._dedup_lock:
            if h in self._seen_hashes:
                return True
            # منع تجاوز الحد الأقصى
            if len(self._seen_hashes) >= _DEDUP_SET_MAX:
                # إزالة نصف العناصر الأقدم (بسيط وفعّال)
                to_remove = list(self._seen_hashes)[:_DEDUP_SET_MAX // 2]
                for h2 in to_remove:
                    self._seen_hashes.discard(h2)
            self._seen_hashes.add(h)
            return False

    def mark_seen(self, data: Any) -> None:
        """تسجيل البيانات كـ seen لمنع تكرارها."""
        h = self._compute_hash(data)
        with self._dedup_lock:
            self._seen_hashes.add(h)

    # ------------------------------------------------------------------
    # JSONL support
    # ------------------------------------------------------------------

    async def append_jsonl(
        self,
        records: List[Dict[str, Any]],
        filepath: Union[str, Path],
        deduplicate: bool = True,
    ) -> int:
        """إضافة سجلات JSONL إلى ملف مع منع التكرار.

        Returns:
            عدد السجلات المكتوبة فعلاً.
        """
        import asyncio
        import fcntl

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        written = 0

        def _write_locked() -> int:
            count = 0
            with open(path, "a", encoding="utf-8") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    for rec in records:
                        if deduplicate and self.is_duplicate(rec):
                            continue
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        count += 1
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            return count

        try:
            written = await asyncio.to_thread(_write_locked)
        except AttributeError:
            # fcntl غير متاح على Windows
            with open(path, "a", encoding="utf-8") as f:
                for rec in records:
                    if deduplicate and self.is_duplicate(rec):
                        continue
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    written += 1

        logger.debug("StorageManager: كُتب %d/%d سجل JSONL → %s", written, len(records), path)
        return written

    async def read_jsonl(self, filepath: Union[str, Path]) -> List[Dict[str, Any]]:
        """قراءة ملف JSONL وإعادة قائمة السجلات."""
        import asyncio

        path = Path(filepath)
        if not path.exists():
            return []

        def _read() -> List[Dict[str, Any]]:
            records = []
            with open(path, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning("StorageManager: سطر JSONL غير صالح %d — %s", line_no, exc)
            return records

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------
    # Cleanup utilities
    # ------------------------------------------------------------------

    async def cleanup_old_files(self, older_than_days: int = 30, layer: str = "raw") -> int:
        """حذف ملفات قديمة من طبقة معينة.

        Args:
            older_than_days: عمر الملف بالأيام.
            layer: الطبقة (raw / bronze / silver / gold).

        Returns:
            عدد الملفات المحذوفة.
        """
        import asyncio
        import time

        layer_paths = {
            "raw": self.base_data_dir / "raw",
            "bronze": self.base_data_dir / "bronze",
            "silver": self.base_data_dir / "silver",
            "gold": self.base_data_dir / "gold",
        }
        target = layer_paths.get(layer)
        if not target or not target.exists():
            return 0

        cutoff = time.time() - (older_than_days * 86400)

        def _delete_old() -> int:
            count = 0
            for f in target.rglob("*"):
                if f.is_file() and f.stat().st_mtime < cutoff:
                    try:
                        f.unlink()
                        count += 1
                    except Exception as exc:
                        logger.warning("cleanup: تعذّر حذف %s — %s", f, exc)
            return count

        deleted = await asyncio.to_thread(_delete_old)
        logger.info("StorageManager: cleanup %s — حُذف %d ملف (أقدم من %d يوم)", layer, deleted, older_than_days)
        return deleted

    async def get_storage_stats(self) -> Dict[str, Any]:
        """إحصائيات التخزين لكل طبقة."""
        import asyncio

        def _calc(path: Path) -> Dict[str, Any]:
            if not path.exists():
                return {"files": 0, "size_mb": 0.0}
            files = list(path.rglob("*"))
            total = sum(f.stat().st_size for f in files if f.is_file())
            return {"files": sum(1 for f in files if f.is_file()), "size_mb": round(total / 1024 / 1024, 2)}

        layers = {
            "raw": self.base_data_dir / "raw",
            "bronze": self.base_data_dir / "bronze",
            "silver": self.base_data_dir / "silver",
            "gold": self.base_data_dir / "gold",
            "metadata": self.base_data_dir / "metadata",
        }
        stats = {}
        for name, path in layers.items():
            stats[name] = await asyncio.to_thread(_calc, path)
        return stats

    # ------------------------------------------------------------------
    # Raw storage
    # ------------------------------------------------------------------

    async def store_raw_response(
        self, data: Union[str, bytes], key: str,
        metadata: Optional[Dict[str, Any]] = None,
        deduplicate: bool = True,
    ) -> str:
        if deduplicate and self.is_duplicate({"key": key, "data": data[:100] if isinstance(data, str) else data[:100].decode("utf-8", errors="ignore")}):
            logger.debug("StorageManager: raw duplicate skipped — %s", key)
            return key
        return await self.raw_storage.save_raw(data, key, metadata)

    async def load_raw_response(self, key: str) -> Union[str, bytes]:
        return await self.raw_storage.load_raw(key)

    # ------------------------------------------------------------------
    # Bronze / Silver / Gold
    # ------------------------------------------------------------------

    async def save_bronze_data(self, data: Dict[str, Any], key: str, schema_name: str,
                                version: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        return await self.bronze_layer.save_processed(data, key, schema_name, version, metadata)

    async def load_bronze_data(self, key: str, schema_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        return await self.bronze_layer.load_processed(key, schema_name, version)

    async def save_silver_data(self, data: Dict[str, Any], key: str, schema_name: str,
                                version: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        return await self.silver_layer.save_processed(data, key, schema_name, version, metadata)

    async def load_silver_data(self, key: str, schema_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        return await self.silver_layer.load_processed(key, schema_name, version)

    async def save_gold_data(self, data: Dict[str, Any], key: str, schema_name: str,
                              version: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        return await self.gold_layer.save_processed(data, key, schema_name, version, metadata)

    async def load_gold_data(self, key: str, schema_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        return await self.gold_layer.load_processed(key, schema_name, version)

    # ------------------------------------------------------------------
    # Article CRUD
    # ------------------------------------------------------------------

    async def save_article(self, article_data: Dict[str, Any]) -> str:
        return await self.article_repo.create(article_data)

    async def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        return await self.article_repo.get(article_id)

    async def update_article(self, article_id: str, updates: Dict[str, Any]) -> None:
        await self.article_repo.update(article_id, updates)

    async def delete_article(self, article_id: str) -> None:
        await self.article_repo.delete(article_id)

    async def archive_article(self, article_id: str) -> None:
        await self.article_repo.update(
            article_id,
            {"is_active": False, "archived_at": datetime.now().isoformat()}
        )

    # ------------------------------------------------------------------
    # Channel CRUD
    # ------------------------------------------------------------------

    async def save_channel(self, channel_data: Dict[str, Any]) -> str:
        return await self.channel_repo.create(channel_data)

    async def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        return await self.channel_repo.get(channel_id)

    async def update_channel(self, channel_id: str, updates: Dict[str, Any]) -> None:
        await self.channel_repo.update(channel_id, updates)

    async def delete_channel(self, channel_id: str) -> None:
        await self.channel_repo.delete(channel_id)

    # ------------------------------------------------------------------
    # Pipeline CRUD
    # ------------------------------------------------------------------

    async def save_pipeline(self, pipeline_data: Dict[str, Any]) -> str:
        return await self.pipeline_repo.create(pipeline_data)

    async def get_pipeline(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        return await self.pipeline_repo.get(pipeline_id)

    async def update_pipeline(self, pipeline_id: str, updates: Dict[str, Any]) -> None:
        await self.pipeline_repo.update(pipeline_id, updates)

    async def delete_pipeline(self, pipeline_id: str) -> None:
        await self.pipeline_repo.delete(pipeline_id)


# ─────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────

_instance: Optional[StorageManager] = None
_instance_lock = threading.Lock()


def get_storage_manager(base_dir: Union[str, Path, None] = None) -> StorageManager:
    """إعادة StorageManager singleton (أو إنشاؤه إذا لم يكن موجوداً)."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = StorageManager(base_data_dir=base_dir or _DEFAULT_BASE_DIR)
        return _instance


def reset_storage_manager() -> None:
    """إعادة تعيين الـ singleton (للاختبار فقط)."""
    global _instance
    with _instance_lock:
        _instance = None
