"""Transform Stage — section 5.14.

Chunks articles and estimates token counts. Stores chunk metadata in
article.metadata.extra for downstream consumers.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from shared.schemas.article import Article
from data_engine.processing.base_processor import BaseProcessor
from data_engine.processing.processing_context import ProcessingContext
from data_engine.processing.transformation.chunker import TextChunker, ChunkerConfig
from data_engine.processing.transformation.tokenizer_wrapper import TokenizerWrapper, TokenizerConfig

logger = logging.getLogger(__name__)


class TransformStage(BaseProcessor):
    """Transforms articles by chunking and estimating token counts.

    Parameters
    ----------
    chunker_config:
        Optional :class:`ChunkerConfig`.
    tokenizer_config:
        Optional :class:`TokenizerConfig`.
    name:
        Stage name.
    """

    def __init__(
        self,
        chunker_config: Optional[ChunkerConfig] = None,
        tokenizer_config: Optional[TokenizerConfig] = None,
        name: str = "transform",
    ) -> None:
        super().__init__(name=name)
        self._chunker = TextChunker(config=chunker_config)
        self._tokenizer = TokenizerWrapper(config=tokenizer_config)

    async def process_articles(
        self,
        articles: List[Article],
        context: ProcessingContext,
    ) -> List[Article]:
        result: List[Article] = []
        total_chunks = 0

        for article in articles:
            chunks = self._chunker.chunk_article(article)
            token_count = self._tokenizer.count_tokens(article.content)
            total_chunks += len(chunks)

            new_extra = dict(article.metadata.extra)
            new_extra["chunk_count"] = len(chunks)
            new_extra["token_count"] = token_count
            new_extra["chunks"] = [
                {
                    "index": c.index,
                    "text": c.text[:200],   # store preview only
                    "estimated_tokens": c.estimated_tokens,
                    "start_char": c.start_char,
                    "end_char": c.end_char,
                }
                for c in chunks
            ]

            new_meta = article.metadata.model_copy(update={"extra": new_extra})
            result.append(article.model_copy(update={"metadata": new_meta}))

        context.set("total_chunks", total_chunks)
        context.set("transform_count", len(result))
        logger.info(
            "%s: transformed %d articles → %d chunks",
            self.name, len(result), total_chunks,
        )
        return result
