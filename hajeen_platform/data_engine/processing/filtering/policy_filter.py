"""Policy Filter — section 5.8.

Applies project-level filtering rules defined in an external YAML config file.

Rules enforced:
- Blocked domains (article URL must not match)
- Blocked keywords (title or content must not contain)
- Minimum content length
- Blacklist support (domain / keyword sets from file)

Config is read from ``configs/filters.yaml`` by default and reloaded on demand.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from shared.schemas.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    """Load a YAML file into a dict. Returns empty dict on any failure."""
    try:
        import yaml  # type: ignore[import]
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data
    except FileNotFoundError:
        logger.warning("PolicyFilter: config not found at %s; using defaults", path)
        return {}
    except Exception as exc:
        logger.error("PolicyFilter: failed to load config %s — %s", path, exc)
        return {}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class PolicyFilterConfig:
    """Policy filter rules."""

    blocked_domains: List[str] = field(default_factory=list)
    blocked_keywords: List[str] = field(default_factory=list)
    min_content_length: int = 50
    blacklist_domains: List[str] = field(default_factory=list)
    blacklist_keywords: List[str] = field(default_factory=list)
    case_sensitive: bool = False
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PolicyFilterConfig":
        """Load config from a YAML file.

        Expected YAML structure::

            policy_filter:
              blocked_domains:
                - spam.com
              blocked_keywords:
                - "casino"
              min_content_length: 100
              blacklist_domains: []
              blacklist_keywords: []

        Parameters
        ----------
        path:
            Path to the YAML config file.

        Returns
        -------
        :class:`PolicyFilterConfig` populated from file.
        """
        data = _load_yaml(Path(path))
        section = data.get("policy_filter", data)

        return cls(
            blocked_domains=section.get("blocked_domains", []),
            blocked_keywords=section.get("blocked_keywords", []),
            min_content_length=int(section.get("min_content_length", 50)),
            blacklist_domains=section.get("blacklist_domains", []),
            blacklist_keywords=section.get("blacklist_keywords", []),
            case_sensitive=bool(section.get("case_sensitive", False)),
        )


# ---------------------------------------------------------------------------
# Policy result
# ---------------------------------------------------------------------------

@dataclass
class PolicyResult:
    """Result of a policy check for a single article."""

    article_id: str
    passes: bool
    rejection_reason: Optional[str] = None
    triggered_rule: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"PolicyResult(id={self.article_id!r} "
            f"passes={self.passes} "
            f"reason={self.rejection_reason!r})"
        )


# ---------------------------------------------------------------------------
# PolicyFilter
# ---------------------------------------------------------------------------

class PolicyFilter:
    """Applies project-level content policy rules.

    Parameters
    ----------
    config:
        :class:`PolicyFilterConfig` or path to ``filters.yaml``.
    """

    _DEFAULT_CONFIG_PATH = Path("configs/filters.yaml")

    def __init__(
        self,
        config: Optional[PolicyFilterConfig] = None,
        config_path: Optional[str | Path] = None,
    ) -> None:
        if config is not None:
            self.config = config
        else:
            path = Path(config_path) if config_path else self._DEFAULT_CONFIG_PATH
            self.config = PolicyFilterConfig.from_yaml(path)

        self._compile_patterns()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_article(self, article: Article) -> PolicyResult:
        """Evaluate *article* against all policy rules.

        Parameters
        ----------
        article:
            Article to evaluate.

        Returns
        -------
        :class:`PolicyResult`.
        """
        cfg = self.config

        # 1. Minimum content length
        if len(article.content.strip()) < cfg.min_content_length:
            return PolicyResult(
                article_id=article.id,
                passes=False,
                rejection_reason=(
                    f"content_too_short "
                    f"(len={len(article.content.strip())} "
                    f"min={cfg.min_content_length})"
                ),
                triggered_rule="min_content_length",
            )

        # 2. Blocked / blacklisted domains
        article_domain = self._extract_domain(str(article.url))
        all_blocked_domains = set(cfg.blocked_domains) | set(cfg.blacklist_domains)
        for domain in all_blocked_domains:
            if article_domain.endswith(domain.lower()):
                return PolicyResult(
                    article_id=article.id,
                    passes=False,
                    rejection_reason=f"blocked_domain ({domain})",
                    triggered_rule="blocked_domain",
                )

        # 3. Blocked / blacklisted keywords
        text = article.title + " " + article.content
        if not cfg.case_sensitive:
            text = text.lower()

        all_blocked_kws = list(cfg.blocked_keywords) + list(cfg.blacklist_keywords)
        for kw in all_blocked_kws:
            needle = kw if cfg.case_sensitive else kw.lower()
            if needle in text:
                return PolicyResult(
                    article_id=article.id,
                    passes=False,
                    rejection_reason=f"blocked_keyword ({kw!r})",
                    triggered_rule="blocked_keyword",
                )

        return PolicyResult(
            article_id=article.id,
            passes=True,
        )

    def filter_batch(
        self, articles: List[Article]
    ) -> Tuple[List[Article], List[PolicyResult]]:
        """Apply policy rules to all *articles*.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        Tuple of ``(kept_articles, all_results)``.
        """
        kept: List[Article] = []
        all_results: List[PolicyResult] = []

        for article in articles:
            result = self.check_article(article)
            all_results.append(result)
            if result.passes:
                kept.append(article)
            else:
                logger.debug(
                    "PolicyFilter: rejected id=%s reason=%s",
                    article.id,
                    result.rejection_reason,
                )

        logger.info(
            "PolicyFilter.filter_batch: in=%d kept=%d rejected=%d",
            len(articles),
            len(kept),
            len(articles) - len(kept),
        )
        return kept, all_results

    def reload_config(self, config_path: Optional[str | Path] = None) -> None:
        """Reload the policy config from disk.

        Parameters
        ----------
        config_path:
            Path override; falls back to the default path.
        """
        path = Path(config_path) if config_path else self._DEFAULT_CONFIG_PATH
        self.config = PolicyFilterConfig.from_yaml(path)
        self._compile_patterns()
        logger.info("PolicyFilter: config reloaded from %s", path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compile_patterns(self) -> None:
        """Pre-compile domain / keyword patterns for fast matching."""
        self._blocked_domains_set = frozenset(
            d.lower()
            for d in (self.config.blocked_domains + self.config.blacklist_domains)
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Return the lowercase netloc of *url*."""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
