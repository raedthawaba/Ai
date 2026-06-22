"""Tokenizer Wrapper — section 5.13.

Unified interface for token counting and text truncation.

Primary backend: tiktoken (OpenAI's fast BPE tokenizer).
Fallback: simple whitespace / character-based estimation.

Provides:
- ``count_tokens(text)``
- ``truncate_tokens(text, max_tokens)``
- ``TokenizerWrapper`` — class-based interface for reuse
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional tiktoken import
# ---------------------------------------------------------------------------

try:
    import tiktoken  # type: ignore[import]
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    logger.info("tokenizer_wrapper: tiktoken not available; using char-based fallback")

# Rough approximation: 1 token ≈ 4 chars for Latin; ≈ 2 chars for Arabic
_CHARS_PER_TOKEN_EN = 4
_CHARS_PER_TOKEN_AR = 2
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TokenizerConfig:
    """Controls tokenization behaviour."""

    encoding: str = "cl100k_base"   # tiktoken encoding name
    language: str = "en"            # "ar" | "en" — affects fallback estimate
    extra: dict = None              # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.extra is None:
            self.extra = {}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _load_tiktoken_encoding(encoding: str):
    """Load a tiktoken encoding, returning None on failure."""
    if not _TIKTOKEN_AVAILABLE:
        return None
    try:
        return tiktoken.get_encoding(encoding)
    except Exception as exc:
        logger.warning("tokenizer_wrapper: tiktoken encoding %r failed — %s", encoding, exc)
        return None


def _estimate_tokens_fallback(text: str, language: str = "en") -> int:
    """Estimate token count without tiktoken.

    Parameters
    ----------
    text:
        Input text.
    language:
        ISO language code.

    Returns
    -------
    Estimated token count.
    """
    if not text:
        return 0
    arabic_ratio = len(_ARABIC_CHAR_RE.findall(text)) / max(len(text), 1)
    chars_per_token = _CHARS_PER_TOKEN_AR if arabic_ratio >= 0.3 else _CHARS_PER_TOKEN_EN
    return max(1, len(text) // chars_per_token)


def count_tokens(
    text: str,
    encoding: str = "cl100k_base",
    language: str = "en",
) -> int:
    """Count the number of tokens in *text*.

    Uses tiktoken when available; falls back to a character-based estimate.

    Parameters
    ----------
    text:
        Input text.
    encoding:
        tiktoken encoding name.
    language:
        ISO language code (used for fallback estimation).

    Returns
    -------
    Token count.
    """
    if not text:
        return 0

    enc = _load_tiktoken_encoding(encoding)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception as exc:
            logger.debug("tiktoken encode failed: %s", exc)

    return _estimate_tokens_fallback(text, language)


def truncate_tokens(
    text: str,
    max_tokens: int,
    encoding: str = "cl100k_base",
    language: str = "en",
) -> str:
    """Truncate *text* to at most *max_tokens* tokens.

    Parameters
    ----------
    text:
        Input text.
    max_tokens:
        Maximum number of tokens.
    encoding:
        tiktoken encoding name.
    language:
        ISO language code (used for fallback).

    Returns
    -------
    Truncated text string.
    """
    if not text or max_tokens <= 0:
        return ""

    enc = _load_tiktoken_encoding(encoding)
    if enc is not None:
        try:
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return enc.decode(tokens[:max_tokens])
        except Exception as exc:
            logger.debug("tiktoken truncate failed: %s", exc)

    # Fallback: estimate chars per token and slice
    arabic_ratio = len(_ARABIC_CHAR_RE.findall(text)) / max(len(text), 1)
    chars_per_token = _CHARS_PER_TOKEN_AR if arabic_ratio >= 0.3 else _CHARS_PER_TOKEN_EN
    max_chars = max_tokens * chars_per_token
    return text[:max_chars].rstrip()


# ---------------------------------------------------------------------------
# TokenizerWrapper class
# ---------------------------------------------------------------------------

class TokenizerWrapper:
    """Reusable tokenizer with persistent encoding state.

    Loads the tiktoken encoding once and reuses it across calls.

    Parameters
    ----------
    config:
        :class:`TokenizerConfig`.
    """

    def __init__(self, config: Optional[TokenizerConfig] = None) -> None:
        self.config = config or TokenizerConfig()
        self._enc = _load_tiktoken_encoding(self.config.encoding)

    @property
    def backend(self) -> str:
        """Return the active tokenization backend."""
        return "tiktoken" if self._enc is not None else "fallback"

    def count_tokens(self, text: str) -> int:
        """Count tokens in *text*.

        Parameters
        ----------
        text:
            Input text.

        Returns
        -------
        Token count.
        """
        if not text:
            return 0
        if self._enc is not None:
            try:
                return len(self._enc.encode(text))
            except Exception:
                pass
        return _estimate_tokens_fallback(text, self.config.language)

    def truncate_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate *text* to *max_tokens* tokens.

        Parameters
        ----------
        text:
            Input text.
        max_tokens:
            Maximum token count.

        Returns
        -------
        Truncated string.
        """
        if not text or max_tokens <= 0:
            return ""
        if self._enc is not None:
            try:
                tokens = self._enc.encode(text)
                if len(tokens) <= max_tokens:
                    return text
                return self._enc.decode(tokens[:max_tokens])
            except Exception:
                pass
        # Fallback
        cfg = self.config
        arabic_ratio = len(_ARABIC_CHAR_RE.findall(text)) / max(len(text), 1)
        cpt = _CHARS_PER_TOKEN_AR if arabic_ratio >= 0.3 else _CHARS_PER_TOKEN_EN
        return text[: max_tokens * cpt].rstrip()

    def batch_count(self, texts: list[str]) -> list[int]:
        """Count tokens for a list of texts.

        Parameters
        ----------
        texts:
            Input texts.

        Returns
        -------
        List of token counts.
        """
        return [self.count_tokens(t) for t in texts]

    def fits_in_context(self, text: str, max_tokens: int) -> bool:
        """Return True when *text* fits within *max_tokens*.

        Parameters
        ----------
        text:
            Input text.
        max_tokens:
            Token budget.

        Returns
        -------
        Boolean.
        """
        return self.count_tokens(text) <= max_tokens
