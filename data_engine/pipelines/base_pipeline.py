"""Base Pipeline — section 5.15.

Abstract base class for all pipelines.
يدعم:
- تسجيل المراحل وتنفيذها تسلسلياً
- retry mechanism للمراحل القابلة للإعادة
- منع انهيار الـ pipeline عند فشل مرحلة واحدة
- قياس execution time لكل مرحلة
- logging احترافي
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.processing_result import ProcessingResult
from shared.schemas.article import Article

logger = logging.getLogger(__name__)

_DEFAULT_STAGE_RETRIES = 1
_DEFAULT_STAGE_RETRY_DELAY = 0.5  # ثانية


class BasePipeline(ABC):
    """Abstract pipeline with stage registration, sequential execution, and retry support.

    Parameters
    ----------
    name:
        Human-readable pipeline name.
    stage_retries:
        عدد مرات إعادة المحاولة لكل مرحلة عند الفشل.
    stage_retry_delay:
        الفاصل الزمني بين المحاولات بالثواني.
    abort_on_empty:
        إيقاف الـ pipeline إذا نفدت المقالات بعد مرحلة ما.
    """

    def __init__(
        self,
        name: str,
        stage_retries: int = _DEFAULT_STAGE_RETRIES,
        stage_retry_delay: float = _DEFAULT_STAGE_RETRY_DELAY,
        abort_on_empty: bool = False,
    ) -> None:
        self.name = name
        self._stages: List[BaseProcessor] = []
        self._stage_retries = max(0, stage_retries)
        self._stage_retry_delay = max(0.0, stage_retry_delay)
        self._abort_on_empty = abort_on_empty

    # ------------------------------------------------------------------
    # Stage management
    # ------------------------------------------------------------------

    def add_stage(self, stage: BaseProcessor) -> "BasePipeline":
        """Register a processing stage (fluent interface)."""
        if not isinstance(stage, BaseProcessor):
            raise TypeError(f"Stage must be a BaseProcessor, got {type(stage)}")
        self._stages.append(stage)
        logger.debug("%s: added stage %r", self.name, stage.name)
        return self

    @property
    def stages(self) -> List[BaseProcessor]:
        """Return the registered stages (read-only view)."""
        return list(self._stages)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(
        self,
        articles: Optional[List[Article]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> ProcessingContext:
        """Execute the pipeline and return the final ProcessingContext."""

    async def _execute_stages(self, context: ProcessingContext) -> ProcessingContext:
        """Run all registered stages sequentially with retry support.

        - كل مرحلة تحاول _stage_retries مرة قبل الاستسلام.
        - فشل مرحلة يُسجَّل ولا يوقف الـ pipeline.
        - abort_on_empty يوقف الـ pipeline إذا نفدت المقالات.
        """
        for stage in self._stages:
            if context.is_aborted:
                logger.warning("%s: pipeline aborted before stage %r", self.name, stage.name)
                break

            if self._abort_on_empty and context.article_count == 0:
                logger.info("%s: aborting — no articles left before stage %r", self.name, stage.name)
                context.abort("no_articles")
                break

            result = await self._run_stage_with_retry(stage, context)

            if result.error_count > 0:
                logger.warning(
                    "%s: stage %r had %d errors",
                    self.name,
                    stage.name,
                    result.error_count,
                )

        logger.info(
            "%s: finished — articles=%d elapsed=%.1fms errors=%d",
            self.name,
            context.article_count,
            context.elapsed_ms,
            len(context.errors),
        )
        return context

    async def _run_stage_with_retry(
        self,
        stage: BaseProcessor,
        context: ProcessingContext,
    ) -> ProcessingResult:
        """تشغيل مرحلة واحدة مع إعادة المحاولة عند الفشل."""
        last_exc: Optional[Exception] = None

        for attempt in range(1 + self._stage_retries):
            stage_start = time.monotonic()
            try:
                result: ProcessingResult = await stage.run(context)
                if attempt > 0:
                    logger.info(
                        "%s: stage %r succeeded on attempt %d/%d",
                        self.name,
                        stage.name,
                        attempt + 1,
                        1 + self._stage_retries,
                    )
                return result

            except Exception as exc:
                last_exc = exc
                elapsed = (time.monotonic() - stage_start) * 1000
                logger.error(
                    "%s: stage %r raised exception (attempt %d/%d, %.1fms): %s",
                    self.name,
                    stage.name,
                    attempt + 1,
                    1 + self._stage_retries,
                    elapsed,
                    exc,
                    exc_info=True,
                )
                context.record_error(stage.name, str(exc), exc=exc)

                if attempt < self._stage_retries:
                    logger.info(
                        "%s: retrying stage %r in %.1fs",
                        self.name,
                        stage.name,
                        self._stage_retry_delay,
                    )
                    await asyncio.sleep(self._stage_retry_delay)

        # كل المحاولات فشلت — نُعيد نتيجة تحمل الأخطاء ولا تُوقف الـ pipeline
        logger.error(
            "%s: stage %r exhausted all %d retries — skipping",
            self.name,
            stage.name,
            1 + self._stage_retries,
        )
        from data_engine.processing.processing_result import ProcessingError
        result = ProcessingResult(
            stage_name=getattr(stage, "name", str(stage)),
            input_count=context.article_count,
            output_articles=list(context.articles),
            rejected_count=0,
            duration_ms=0.0,
        )
        if last_exc:
            result.errors.append(
                ProcessingError(
                    stage=getattr(stage, "name", str(stage)),
                    message=str(last_exc),
                    exc_type=type(last_exc).__name__,
                )
            )
        return result
