"""Entity Extractor — section 5.10.

Extracts named entities from article text.

Primary engine: spaCy lightweight models (``en_core_web_sm``, ``ar_core_news_sm``).
Fallback: regex-based heuristic patterns (no spaCy required).

Supports Arabic and English.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from shared.schemas.article import Article, ArticleEntity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional spaCy import
# ---------------------------------------------------------------------------

try:
    import spacy  # type: ignore[import]
    _SPACY_AVAILABLE = True
except ImportError:
    _SPACY_AVAILABLE = False
    logger.info("entity_extractor: spaCy not available; using regex fallback")


# ---------------------------------------------------------------------------
# Regex fallback patterns
# ---------------------------------------------------------------------------

# Person-like: capitalised words (English)
_PERSON_EN_RE = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+\b")

# Org-like: abbreviations (English)
_ORG_EN_RE = re.compile(r"\b(?:[A-Z]{2,}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Inc|Corp|Ltd|LLC|Foundation|Institute|University|Organization|Organisation))\b")

# Location-like: common English location suffixes
_LOC_EN_RE = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*"
    r"(?:City|Country|Street|Avenue|Province|State|Island|Ocean|Sea|River|Lake|Mountain)\b"
)

# Arabic: persons often follow هـ ال honorifics
_PERSON_AR_RE = re.compile(
    r"(?:السيد|السيدة|الدكتور|الدكتورة|الأستاذ|الشيخ|الأمير|الأميرة|الرئيس|الوزير)\s+"
    r"([\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,}){0,3})"
)

# Arabic org
_ORG_AR_RE = re.compile(
    r"(?:شركة|منظمة|مؤسسة|جمعية|اتحاد|هيئة|وزارة|جامعة|بنك|مصرف)\s+"
    r"([\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,}){0,3})"
)

# Arabic cities / countries (common nouns that appear after في / من)
_LOC_AR_RE = re.compile(
    r"(?:في|من|إلى|بـ|داخل|خارج)\s+([\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,})?)"
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EntityExtractorConfig:
    """Controls entity extraction behaviour."""

    extract_persons: bool = True
    extract_orgs: bool = True
    extract_locations: bool = True
    min_text_length: int = 20
    max_entities: int = 50
    model_en: str = "en_core_web_sm"
    model_ar: str = "ar_core_news_sm"
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SpaCy-based extraction
# ---------------------------------------------------------------------------

class _SpaCyExtractor:
    """Wraps loaded spaCy models for entity extraction."""

    def __init__(self, model_en: str, model_ar: str) -> None:
        self._nlp_cache: Dict[str, object] = {}
        self._model_en = model_en
        self._model_ar = model_ar

    def _get_nlp(self, language: str):
        model_name = self._model_ar if language == "ar" else self._model_en
        if model_name in self._nlp_cache:
            return self._nlp_cache[model_name]
        try:
            nlp = spacy.load(model_name)
            self._nlp_cache[model_name] = nlp
            return nlp
        except OSError:
            logger.warning(
                "spaCy model %r not found; falling back to regex", model_name
            )
            return None

    def extract(
        self, text: str, language: str, wanted_labels: frozenset[str]
    ) -> List[ArticleEntity]:
        nlp = self._get_nlp(language)
        if nlp is None:
            return []

        entities: List[ArticleEntity] = []
        try:
            doc = nlp(text[:100_000])  # cap for memory safety
            for ent in doc.ents:
                if ent.label_ not in wanted_labels:
                    continue
                try:
                    entities.append(
                        ArticleEntity(
                            text=ent.text.strip(),
                            label=ent.label_,
                            start_char=ent.start_char,
                            end_char=ent.end_char,
                            score=1.0,
                        )
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("spaCy extraction error: %s", exc)

        return entities


# Singleton — only one loader even if multiple extractors exist
_spacy_extractor: Optional[_SpaCyExtractor] = None


def _get_spacy_extractor(cfg: EntityExtractorConfig) -> _SpaCyExtractor:
    global _spacy_extractor
    if _spacy_extractor is None:
        _spacy_extractor = _SpaCyExtractor(cfg.model_en, cfg.model_ar)
    return _spacy_extractor


# ---------------------------------------------------------------------------
# Regex-based fallback extraction
# ---------------------------------------------------------------------------

def _regex_extract(
    text: str,
    language: str,
    extract_persons: bool,
    extract_orgs: bool,
    extract_locations: bool,
) -> List[ArticleEntity]:
    """Extract entities using regex heuristics."""
    entities: List[ArticleEntity] = []
    seen: set = set()

    def _add(m: re.Match, label: str, group: int = 0) -> None:
        span = m.group(group).strip()
        key = (span.lower(), label)
        if key in seen or not span:
            return
        seen.add(key)
        try:
            entities.append(
                ArticleEntity(
                    text=span,
                    label=label,
                    start_char=m.start(group),
                    end_char=m.end(group),
                    score=0.6,
                )
            )
        except Exception:
            pass

    if language == "ar":
        if extract_persons:
            for m in _PERSON_AR_RE.finditer(text):
                _add(m, "PERSON", group=1)
        if extract_orgs:
            for m in _ORG_AR_RE.finditer(text):
                _add(m, "ORG", group=1)
        if extract_locations:
            for m in _LOC_AR_RE.finditer(text):
                _add(m, "LOC", group=1)
    else:
        if extract_persons:
            for m in _PERSON_EN_RE.finditer(text):
                _add(m, "PERSON")
        if extract_orgs:
            for m in _ORG_EN_RE.finditer(text):
                _add(m, "ORG")
        if extract_locations:
            for m in _LOC_EN_RE.finditer(text):
                _add(m, "LOC")

    return entities


# ---------------------------------------------------------------------------
# EntityExtractor class
# ---------------------------------------------------------------------------

class EntityExtractor:
    """Extracts named entities (persons, organisations, locations) from text.

    Uses spaCy when available, falls back to regex heuristics.

    Parameters
    ----------
    config:
        :class:`EntityExtractorConfig`.
    """

    _LABEL_MAP = {
        "PER": "PERSON", "PERSON": "PERSON",
        "ORG": "ORG",
        "GPE": "LOC", "LOC": "LOC", "LOCATION": "LOC",
    }

    def __init__(self, config: Optional[EntityExtractorConfig] = None) -> None:
        self.config = config or EntityExtractorConfig()

    def extract(self, text: str, language: str = "en") -> List[ArticleEntity]:
        """Extract entities from *text*.

        Parameters
        ----------
        text:
            Input text.
        language:
            ISO language code (``"ar"`` or ``"en"``).

        Returns
        -------
        List of :class:`ArticleEntity`.
        """
        cfg = self.config
        if not text or len(text.strip()) < cfg.min_text_length:
            return []

        wanted = self._build_wanted_set()

        if _SPACY_AVAILABLE:
            extractor = _get_spacy_extractor(cfg)
            entities = extractor.extract(text, language, wanted)
            if entities:
                return self._normalise(entities)[: cfg.max_entities]

        # Regex fallback
        entities = _regex_extract(
            text,
            language=language,
            extract_persons=cfg.extract_persons,
            extract_orgs=cfg.extract_orgs,
            extract_locations=cfg.extract_locations,
        )
        return self._normalise(entities)[: cfg.max_entities]

    def extract_article_entities(self, article: Article) -> List[ArticleEntity]:
        """Extract entities from an article's combined text.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        List of :class:`ArticleEntity`.
        """
        text = article.title + " " + article.content
        lang = article.metadata.language or "en"
        return self.extract(text, language=lang)

    def enrich_article(self, article: Article) -> Article:
        """Return a new article with entities merged into ``metadata.entities``.

        Parameters
        ----------
        article:
            Source article.

        Returns
        -------
        New Article with enriched entities list.
        """
        new_entities = self.extract_article_entities(article)
        if not new_entities:
            return article

        existing = list(article.metadata.entities)
        existing_spans = {(e.start_char, e.end_char) for e in existing}
        for ent in new_entities:
            if (ent.start_char, ent.end_char) not in existing_spans:
                existing.append(ent)
                existing_spans.add((ent.start_char, ent.end_char))

        new_meta = article.metadata.model_copy(update={"entities": existing})
        enriched = article.model_copy(update={"metadata": new_meta})

        logger.debug(
            "EntityExtractor: id=%s new_entities=%d",
            article.id,
            len(new_entities),
        )
        return enriched

    def enrich_batch(self, articles: List[Article]) -> List[Article]:
        """Enrich a list of articles with entity extraction.

        Parameters
        ----------
        articles:
            Input articles.

        Returns
        -------
        List of enriched Article copies.
        """
        result = [self.enrich_article(a) for a in articles]
        logger.info("EntityExtractor.enrich_batch: processed=%d", len(result))
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_wanted_set(self) -> frozenset:
        cfg = self.config
        wanted = set()
        if cfg.extract_persons:
            wanted.update({"PERSON", "PER"})
        if cfg.extract_orgs:
            wanted.add("ORG")
        if cfg.extract_locations:
            wanted.update({"GPE", "LOC", "LOCATION"})
        return frozenset(wanted)

    def _normalise(self, entities: List[ArticleEntity]) -> List[ArticleEntity]:
        """Normalise entity labels to consistent values."""
        result = []
        for ent in entities:
            mapped = self._LABEL_MAP.get(ent.label, ent.label)
            result.append(
                ArticleEntity(
                    text=ent.text,
                    label=mapped,
                    start_char=ent.start_char,
                    end_char=ent.end_char,
                    score=ent.score,
                )
            )
        return result
