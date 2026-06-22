"""Channel Registry — إدارة دورة حياة القنوات مع استمرارية SQLite.

يدعم:
- حفظ القنوات في SQLite واسترجاعها بعد restart
- منع duplicate channel IDs
- threading lock للعمليات المتزامنة
- validation كامل للـ configs
- ACTIVE / PAUSED / ERROR / INACTIVE states
- تتبع last_run + إحصائيات
- audit logging لكل العمليات
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from shared.schemas.channel import ChannelConfig, ChannelStats, ChannelStatus
from data_engine.channels.base import BaseChannel
from shared.exceptions import ChannelException

logger = logging.getLogger(__name__)

_DB_PATH = Path("storage_data/metadata/channels.db")
_DB_LOCK = threading.RLock()


# ─────────────────────────────────────────────
# SQLite helpers
# ─────────────────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    """إنشاء/ترقية قاعدة بيانات SQLite للقنوات."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            config_json TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT DEFAULT (datetime('now','utc')),
            updated_at  TEXT DEFAULT (datetime('now','utc'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_audit (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id  TEXT NOT NULL,
            action      TEXT NOT NULL,
            actor       TEXT NOT NULL DEFAULT 'system',
            detail      TEXT,
            timestamp   TEXT DEFAULT (datetime('now','utc'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_stats (
            channel_id      TEXT PRIMARY KEY,
            total_runs      INTEGER DEFAULT 0,
            successful_runs INTEGER DEFAULT 0,
            failed_runs     INTEGER DEFAULT 0,
            total_fetched   INTEGER DEFAULT 0,
            total_processed INTEGER DEFAULT 0,
            total_stored    INTEGER DEFAULT 0,
            last_run_at     TEXT,
            last_run_status TEXT,
            last_error      TEXT,
            updated_at      TEXT DEFAULT (datetime('now','utc'))
        )
    """)
    conn.commit()
    return conn


def _audit(conn: sqlite3.Connection, channel_id: str, action: str, detail: str = "") -> None:
    """تسجيل audit log لعملية على قناة."""
    try:
        conn.execute(
            "INSERT INTO channel_audit (channel_id, action, detail) VALUES (?, ?, ?)",
            (channel_id, action, detail[:500] if detail else ""),
        )
    except Exception as exc:
        logger.warning("channel_registry: audit log error — %s", exc)


def _save_channel_to_db(config: ChannelConfig) -> None:
    """حفظ أو تحديث تكوين القناة في SQLite."""
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            config_json = config.model_dump_json()
            conn.execute("""
                INSERT OR REPLACE INTO channels (id, name, config_json, status, updated_at)
                VALUES (?, ?, ?, ?, datetime('now','utc'))
            """, (config.id, config.name, config_json, config.status.value))
            # حفظ الإحصائيات
            stats = config.stats
            conn.execute("""
                INSERT OR REPLACE INTO channel_stats
                (channel_id, total_runs, successful_runs, failed_runs,
                 total_fetched, total_processed, total_stored,
                 last_run_at, last_run_status, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','utc'))
            """, (
                config.id,
                stats.total_runs,
                stats.successful_runs,
                stats.failed_runs,
                stats.total_fetched,
                stats.total_processed,
                stats.total_stored,
                stats.last_run_at.isoformat() if stats.last_run_at else None,
                stats.last_run_status,
                stats.last_error,
            ))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("channel_registry: خطأ في حفظ القناة %s — %s", config.id, exc)


def _delete_channel_from_db(channel_id: str) -> None:
    """حذف تكوين القناة من SQLite."""
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
            conn.execute("DELETE FROM channel_stats WHERE channel_id = ?", (channel_id,))
            _audit(conn, channel_id, "DELETE")
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("channel_registry: خطأ في حذف القناة %s — %s", channel_id, exc)


def _load_all_configs_from_db() -> List[ChannelConfig]:
    """استرجاع جميع تكوينات القنوات من SQLite مع إحصائياتها."""
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            rows = conn.execute(
                "SELECT c.config_json, s.total_runs, s.successful_runs, s.failed_runs, "
                "s.total_fetched, s.total_processed, s.total_stored, "
                "s.last_run_at, s.last_run_status, s.last_error "
                "FROM channels c LEFT JOIN channel_stats s ON c.id = s.channel_id"
            ).fetchall()
            conn.close()

            configs = []
            for row in rows:
                try:
                    cfg = ChannelConfig.model_validate_json(row[0])
                    # ترميم الإحصائيات من جدول stats إذا كانت محفوظة
                    if row[1] is not None:
                        cfg.stats = ChannelStats(
                            total_runs=row[1] or 0,
                            successful_runs=row[2] or 0,
                            failed_runs=row[3] or 0,
                            total_fetched=row[4] or 0,
                            total_processed=row[5] or 0,
                            total_stored=row[6] or 0,
                            last_run_at=datetime.fromisoformat(row[7]) if row[7] else None,
                            last_run_status=row[8],
                            last_error=row[9],
                        )
                    configs.append(cfg)
                except Exception as exc:
                    logger.warning("channel_registry: تعذّر تحليل تكوين — %s", exc)
            return configs
        except Exception as exc:
            logger.error("channel_registry: خطأ في استرجاع القنوات — %s", exc)
            return []


def _get_audit_log(channel_id: str, limit: int = 50) -> List[dict]:
    """استرجاع سجل audit لقناة."""
    with _DB_LOCK:
        try:
            conn = _ensure_db()
            rows = conn.execute(
                "SELECT action, actor, detail, timestamp FROM channel_audit "
                "WHERE channel_id = ? ORDER BY id DESC LIMIT ?",
                (channel_id, limit),
            ).fetchall()
            conn.close()
            return [
                {"action": r[0], "actor": r[1], "detail": r[2], "timestamp": r[3]}
                for r in rows
            ]
        except Exception as exc:
            logger.error("channel_registry: خطأ في قراءة audit log — %s", exc)
            return []


# ─────────────────────────────────────────────
# ChannelRegistry
# ─────────────────────────────────────────────

class ChannelRegistry:
    """إدارة دورة حياة القنوات في الذاكرة مع استمرارية SQLite."""

    _channels: Dict[str, BaseChannel] = {}
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def register(cls, channel: BaseChannel, actor: str = "system") -> None:
        """تسجيل قناة وحفظها في SQLite مع audit log."""
        if not isinstance(channel, BaseChannel):
            raise ChannelException("كائن القناة غير صالح للتسجيل.")

        cid = channel.config.id
        with cls._lock:
            if cid in cls._channels:
                raise ChannelException(f"القناة '{cid}' مسجّلة بالفعل.")
            cls._channels[cid] = channel

        _save_channel_to_db(channel.config)

        with _DB_LOCK:
            try:
                conn = _ensure_db()
                _audit(conn, cid, "REGISTER", f"name={channel.config.name} actor={actor}")
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("channel_registry: audit error — %s", exc)

        logger.info("channel_registry: سُجّلت القناة %s (%s)", cid, channel.config.name)

    @classmethod
    def unregister(cls, channel_id: str, actor: str = "system") -> None:
        """إلغاء تسجيل القناة وحذفها من SQLite."""
        with cls._lock:
            if channel_id not in cls._channels:
                raise ChannelException(f"القناة '{channel_id}' غير موجودة.")
            del cls._channels[channel_id]

        _delete_channel_from_db(channel_id)
        logger.info("channel_registry: أُلغي تسجيل القناة %s", channel_id)

    @classmethod
    def get(cls, channel_id: str) -> Optional[BaseChannel]:
        """استرجاع قناة بمعرّفها."""
        with cls._lock:
            return cls._channels.get(channel_id)

    @classmethod
    def list_all(cls) -> List[BaseChannel]:
        """إدراج جميع القنوات المسجّلة."""
        with cls._lock:
            return list(cls._channels.values())

    @classmethod
    def update_status(cls, channel_id: str, new_status: ChannelStatus, actor: str = "system") -> None:
        """تحديث حالة القناة في الذاكرة وفي SQLite."""
        with cls._lock:
            channel = cls._channels.get(channel_id)
            if not channel:
                raise ChannelException(f"القناة '{channel_id}' غير موجودة لتحديث الحالة.")
            old_status = channel.config.status
            channel.update_status(new_status)

        _save_channel_to_db(channel.config)

        with _DB_LOCK:
            try:
                conn = _ensure_db()
                _audit(
                    conn, channel_id, "STATUS_CHANGE",
                    f"{old_status.value} → {new_status.value} actor={actor}",
                )
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.warning("channel_registry: audit error — %s", exc)

        logger.info("channel_registry: حالة القناة %s → %s", channel_id, new_status.value)

    @classmethod
    def update_stats(cls, channel_id: str) -> None:
        """حفظ إحصائيات القناة الحالية في SQLite."""
        with cls._lock:
            channel = cls._channels.get(channel_id)
        if channel:
            _save_channel_to_db(channel.config)

    @classmethod
    async def restore_from_db(cls) -> int:
        """استعادة القنوات من SQLite عند بدء تشغيل التطبيق."""
        from data_engine.channels.builder import ChannelBuilder

        configs = _load_all_configs_from_db()
        restored = 0
        for config in configs:
            with cls._lock:
                if config.id in cls._channels:
                    continue
            try:
                channel = await ChannelBuilder.create_from_config(config)
                with cls._lock:
                    cls._channels[channel.config.id] = channel
                restored += 1
                logger.info("channel_registry: استُعيدت القناة %s من SQLite", config.id)
            except Exception as exc:
                logger.warning("channel_registry: تعذّر استعادة القناة %s — %s", config.id, exc)

        logger.info("channel_registry: استُعيدت %d قناة من SQLite", restored)
        return restored

    @classmethod
    def get_audit_log(cls, channel_id: str, limit: int = 50) -> List[dict]:
        """استرجاع سجل audit للقناة."""
        return _get_audit_log(channel_id, limit=limit)

    @classmethod
    def clear(cls) -> None:
        """مسح جميع القنوات من الذاكرة (للاختبار فقط)."""
        with cls._lock:
            cls._channels.clear()

    @classmethod
    def list_from_db(cls) -> List[ChannelConfig]:
        """استرجاع تكوينات القنوات مباشرة من SQLite."""
        return _load_all_configs_from_db()

    @classmethod
    def count(cls) -> int:
        """عدد القنوات المسجّلة في الذاكرة."""
        with cls._lock:
            return len(cls._channels)
