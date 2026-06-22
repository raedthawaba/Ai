"""Ingestion Tasks — section 6.3.

Celery tasks for background channel ingestion.

Tasks:
- run_channel_ingestion  — fetch + process a single channel
- validate_sources_task  — validate source URLs for all channels
- refresh_channel_task   — force-refresh a specific channel
- health_check_task      — periodic heartbeat
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: run async code from Celery task (synchronous context)
# ---------------------------------------------------------------------------

def _run(coro):
    """Execute a coroutine from synchronous Celery task code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 6.3.1 — run_channel_ingestion
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.ingestion_tasks.run_channel_ingestion",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def run_channel_ingestion(self, channel_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch and process a single channel in the background.

    Parameters
    ----------
    channel_id:
        ID of the registered channel.
    config:
        Optional runtime config overrides.

    Returns
    -------
    Dict with ``fetched``, ``processed``, ``channel_id``, ``run_id``.
    """
    logger.info("run_channel_ingestion: starting channel_id=%s", channel_id)

    async def _run_ingestion():
        from data_engine.channels.registry import ChannelRegistry
        from data_engine.channels.predefined.news_channel import NewsChannel
        from data_engine.channels.predefined.demo_channel import DemoChannel

        channel = ChannelRegistry.get(channel_id)
        if channel is None:
            raise ValueError(f"Channel not found: {channel_id!r}")

        fetch_result = await channel.fetch()
        articles = fetch_result.articles
        logger.info(
            "run_channel_ingestion: channel=%s fetched=%d",
            channel_id, len(articles),
        )

        processed = await channel.run_pipeline(articles)
        logger.info(
            "run_channel_ingestion: channel=%s processed=%d",
            channel_id, len(processed),
        )
        return {
            "channel_id": channel_id,
            "fetched": len(articles),
            "processed": len(processed),
            "task_id": self.request.id,
        }

    try:
        return _run(_run_ingestion())
    except ValueError as exc:
        logger.error("run_channel_ingestion: %s", exc)
        raise
    except Exception as exc:
        logger.error("run_channel_ingestion: error — %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 6.3.2 — validate_sources_task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.ingestion_tasks.validate_sources_task",
    max_retries=2,
    default_retry_delay=15,
    track_started=True,
)
def validate_sources_task(self, channel_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Validate source URLs for channels.

    Parameters
    ----------
    channel_ids:
        List of channel IDs. When ``None``, validates all registered channels.

    Returns
    -------
    Dict mapping channel_id → bool (valid).
    """
    logger.info("validate_sources_task: channel_ids=%s", channel_ids)

    async def _validate():
        from data_engine.channels.registry import ChannelRegistry

        channels = ChannelRegistry.list_all()
        if channel_ids:
            channels = [c for c in channels if c.config.id in channel_ids]

        results: Dict[str, bool] = {}
        for channel in channels:
            try:
                valid = await channel.validate_source()
                results[channel.config.id] = valid
                logger.debug("validate_sources_task: %s → %s", channel.config.id, valid)
            except Exception as exc:
                logger.warning(
                    "validate_sources_task: %s failed — %s", channel.config.id, exc
                )
                results[channel.config.id] = False
        return {"results": results, "total": len(results)}

    try:
        return _run(_validate())
    except Exception as exc:
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 6.3.3 — refresh_channel_task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.ingestion_tasks.refresh_channel_task",
    max_retries=3,
    default_retry_delay=60,
    track_started=True,
)
def refresh_channel_task(self, channel_id: str) -> Dict[str, Any]:
    """Force-refresh a specific channel — re-fetch from source.

    Parameters
    ----------
    channel_id:
        ID of the channel to refresh.
    """
    logger.info("refresh_channel_task: channel_id=%s", channel_id)
    return run_channel_ingestion.apply(args=[channel_id]).result


# ---------------------------------------------------------------------------
# 6.3.4 — health_check_task (periodic)
# ---------------------------------------------------------------------------

@shared_task(
    name="workers.tasks.ingestion_tasks.health_check_task",
    ignore_result=False,
)
def health_check_task() -> Dict[str, Any]:
    """Periodic heartbeat task — verifies workers are alive."""
    import time
    from data_engine.channels.registry import ChannelRegistry

    channels = ChannelRegistry.list_all()
    logger.info("health_check_task: registered_channels=%d", len(channels))
    return {
        "status": "ok",
        "timestamp": time.time(),
        "registered_channels": len(channels),
    }
