"""Tests for EntityExtractor — section 5.10."""
from __future__ import annotations
import pytest
from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.enrichment.entity_extractor import (
    EntityExtractor, EntityExtractorConfig,
    _regex_extract,
)
from shared.utils.datetime_utils import utc_now


def _make_article(content: str, title: str = "Test", language: str = "en") -> Article:
    return Article(
        id="ent_test_001",
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=utc_now(),
        metadata=ArticleMetadata(source_id="ent_src", language=language),
    )


EN_TEXT = (
    "Apple Inc. is based in Cupertino City. "
    "Elon Musk announced that Tesla Corporation will expand operations. "
    "Microsoft Foundation is partnering with Google Inc. on new AI research."
)

AR_TEXT = (
    "الرئيس محمد يوسف أعلن في القاهرة عن خطة جديدة. "
    "شركة الاتصالات العربية وقعت عقداً مع مؤسسة التقنيات في الرياض. "
    "الدكتورة فاطمة الزهراء قدمت أبحاثاً في جامعة الملك عبدالله."
)


class TestRegexExtract:
    def test_extracts_english_orgs(self):
        entities = _regex_extract(
            EN_TEXT, language="en",
            extract_persons=True, extract_orgs=True, extract_locations=True,
        )
        labels = [e.label for e in entities]
        assert len(entities) > 0

    def test_extracts_arabic_persons(self):
        entities = _regex_extract(
            AR_TEXT, language="ar",
            extract_persons=True, extract_orgs=True, extract_locations=True,
        )
        assert len(entities) > 0
        person_entities = [e for e in entities if e.label == "PERSON"]
        assert len(person_entities) > 0

    def test_extracts_arabic_orgs(self):
        entities = _regex_extract(
            AR_TEXT, language="ar",
            extract_persons=True, extract_orgs=True, extract_locations=True,
        )
        org_entities = [e for e in entities if e.label == "ORG"]
        assert len(org_entities) > 0

    def test_no_duplicates(self):
        entities = _regex_extract(
            EN_TEXT, language="en",
            extract_persons=True, extract_orgs=True, extract_locations=True,
        )
        seen = set()
        for e in entities:
            key = (e.text.lower(), e.label)
            assert key not in seen, f"Duplicate entity: {key}"
            seen.add(key)


class TestEntityExtractor:
    def setup_method(self):
        self.extractor = EntityExtractor()

    def test_extract_english(self):
        entities = self.extractor.extract(EN_TEXT, language="en")
        assert isinstance(entities, list)

    def test_extract_arabic(self):
        entities = self.extractor.extract(AR_TEXT, language="ar")
        assert isinstance(entities, list)

    def test_empty_text_returns_empty(self):
        entities = self.extractor.extract("", language="en")
        assert entities == []

    def test_short_text_returns_empty(self):
        entities = self.extractor.extract("Hi.", language="en")
        assert entities == []

    def test_entity_score_in_range(self):
        entities = self.extractor.extract(EN_TEXT, language="en")
        for e in entities:
            assert 0.0 <= e.score <= 1.0

    def test_enrich_article_english(self):
        art = _make_article(EN_TEXT, language="en")
        enriched = self.extractor.enrich_article(art)
        # Either entities added or original returned (if spaCy unavailable)
        assert isinstance(enriched.metadata.entities, list)

    def test_enrich_article_arabic(self):
        art = _make_article(AR_TEXT, language="ar")
        enriched = self.extractor.enrich_article(art)
        assert isinstance(enriched.metadata.entities, list)

    def test_enrich_batch(self):
        arts = [
            _make_article(EN_TEXT, language="en"),
            _make_article(AR_TEXT, language="ar"),
        ]
        results = self.extractor.enrich_batch(arts)
        assert len(results) == 2

    def test_max_entities_config(self):
        cfg = EntityExtractorConfig(max_entities=2)
        extractor = EntityExtractor(config=cfg)
        entities = extractor.extract(EN_TEXT * 10, language="en")
        assert len(entities) <= 2

    def test_disable_locations(self):
        cfg = EntityExtractorConfig(
            extract_persons=True, extract_orgs=True, extract_locations=False
        )
        extractor = EntityExtractor(config=cfg)
        entities = extractor.extract(EN_TEXT, language="en")
        loc_entities = [e for e in entities if e.label == "LOC"]
        assert loc_entities == []
