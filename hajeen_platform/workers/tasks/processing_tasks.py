"""Processing Tasks — section 6.4.

Celery tasks for background article processing.

Tasks:
- process_article_batch      — run full pipeline on a serialised batch
- clean_articles_task        — clean-only pass
- enrich_articles_task       — enrich-only pass
- deduplicate_articles_task  — dedup-only pass
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _deserialise_articles(raw: List[Dict[str, Any]]):
    """Convert raw dicts back to Article objects."""
    from shared.schemas.article import Article
    articles = []
    for d in raw:
        try:
            articles.append(Article.model_validate(d))
        except Exception as exc:
            logger.warning("_deserialise_articles: skipping — %s", exc)
    return articles


def _serialise_articles(articles) -> List[Dict[str, Any]]:
    """Convert Article objects to JSON-serialisable dicts."""
    return [a.model_dump(mode="json") for a in articles]


# ---------------------------------------------------------------------------
# 6.4.1 — process_article_batch
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.processing_tasks.process_article_batch",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
)
def process_article_batch(
    self,
    articles_raw: List[Dict[str, Any]],
    source_id: str = "batch",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the full processing pipeline on a batch of articles.

    Parameters
    ----------
    articles_raw:
        List of article dicts (JSON-serialised Article objects).
    source_id:
        Source identifier passed to the pipeline context.
    config:
        Optional pipeline config overrides.

    Returns
    -------
    Dict with ``input_count``, ``output_count``, ``rejection_rate``,
    ``errors``, ``output_articles``.
    """
    logger.info(
        "process_article_batch: source=%s input=%d", source_id, len(articles_raw)
    )

    async def _process():
        from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
        from data_engine.processing.filtering.policy_filter import PolicyFilterConfig

        articles = _deserialise_articles(articles_raw)
        if not articles:
            return {
                "source_id": source_id,
                "input_count": 0,
                "output_count": 0,
                "rejection_rate": 0.0,
                "errors": [],
                "output_articles": [],
            }

        policy_cfg = PolicyFilterConfig(min_content_length=30)
        orch = PipelineOrchestrator(
            name=f"batch_{source_id}",
            source_id=source_id,
            policy_config=policy_cfg,
        )

        ctx = await orch.run(articles=articles, config=config or {})
        metrics = orch.last_metrics

        return {
            "source_id": source_id,
            "task_id": self.request.id,
            "input_count": metrics.input_count if metrics else len(articles_raw),
            "output_count": ctx.article_count,
            "rejection_rate": metrics.rejection_rate if metrics else 0.0,
            "errors": [str(e) for e in ctx.errors[:10]],
            "output_articles": _serialise_articles(ctx.articles),
        }

    try:
        return _run(_process())
    except Exception as exc:
        logger.error("process_article_batch: error — %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 6.4.2 — clean_articles_task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.processing_tasks.clean_articles_task",
    max_retries=2,
    track_started=True,
)
def clean_articles_task(
    self, articles_raw: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """HTML cleaning + text normalisation only.

    Parameters
    ----------
    articles_raw:
        List of article dicts.

    Returns
    -------
    Dict with ``output_articles``.
    """
    logger.info("clean_articles_task: input=%d", len(articles_raw))

    try:
        from data_engine.processing.cleaning.html_cleaner import HTMLCleaner
        from data_engine.processing.cleaning.text_normalizer import TextNormalizer

        articles = _deserialise_articles(articles_raw)
        cleaner = HTMLCleaner()
        normalizer = TextNormalizer()

        cleaned = cleaner.clean_batch(articles)
        normalised = normalizer.normalize_batch(cleaned)

        return {
            "task_id": self.request.id,
            "input_count": len(articles),
            "output_count": len(normalised),
            "output_articles": _serialise_articles(normalised),
        }
    except Exception as exc:
        logger.error("clean_articles_task: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 6.4.3 — enrich_articles_task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.processing_tasks.enrich_articles_task",
    max_retries=2,
    track_started=True,
)
def enrich_articles_task(
    self, articles_raw: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Keyword + entity + summary enrichment only.

    Parameters
    ----------
    articles_raw:
        List of article dicts.

    Returns
    -------
    Dict with ``output_articles``.
    """
    logger.info("enrich_articles_task: input=%d", len(articles_raw))

    try:
        from data_engine.processing.enrichment.keyword_extractor import KeywordExtractor
        from data_engine.processing.enrichment.entity_extractor import EntityExtractor
        from data_engine.processing.enrichment.summarizer import Summarizer

        articles = _deserialise_articles(articles_raw)
        kw = KeywordExtractor()
        ent = EntityExtractor()
        summ = Summarizer()

        enriched = kw.enrich_batch(articles)
        enriched = ent.enrich_batch(enriched)
        enriched = summ.summarize_batch(enriched)

        return {
            "task_id": self.request.id,
            "input_count": len(articles),
            "output_count": len(enriched),
            "output_articles": _serialise_articles(enriched),
        }
    except Exception as exc:
        logger.error("enrich_articles_task: %s", exc)
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# 6.4.4 — deduplicate_articles_task
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="workers.tasks.processing_tasks.deduplicate_articles_task",
    max_retries=2,
    track_started=True,
)
def deduplicate_articles_task(
    self, articles_raw: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Deduplication-only pass.

    Parameters
    ----------
    articles_raw:
        List of article dicts.

    Returns
    -------
    Dict with ``unique_articles``, ``duplicate_count``.
    """
    logger.info("deduplicate_articles_task: input=%d", len(articles_raw))

    try:
        from data_engine.processing.filtering.deduplicator import Deduplicator

        articles = _deserialise_articles(articles_raw)
        dedup = Deduplicator()
        result = dedup.deduplicate(articles)

        return {
            "task_id": self.request.id,
            "input_count": len(articles),
            "unique_count": len(result.unique_articles),
            "duplicate_count": result.duplicate_count,
            "output_articles": _serialise_articles(result.unique_articles),
        }
    except Exception as exc:
        logger.error("deduplicate_articles_task: %s", exc)
        raise self.retry(exc=exc)
