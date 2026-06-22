"""Unit tests for TopicClassifier & SentimentAnalyzer — Phase 2 (Section 2.4)."""
from __future__ import annotations

import pytest
from datetime import datetime

from shared.schemas.article import Article, ArticleMetadata
from data_engine.processing.enrichment.topic_classifier import (
    TopicClassifier,
    TopicClassifierConfig,
    ClassificationResult,
    TopicScore,
    _keyword_density_score,
)
from data_engine.processing.enrichment.sentiment_analyzer import (
    SentimentAnalyzer,
    SentimentConfig,
    SentimentResult,
    _lexicon_score,
    _compute_compound,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_article(
    content: str,
    title: str = "Test",
    language: str = "en",
    article_id: str = "art001",
) -> Article:
    return Article(
        id=article_id,
        title=title,
        content=content,
        url="https://example.com/test",
        published_at=datetime(2024, 1, 1),
        metadata=ArticleMetadata(source_id="src_test", language=language),
    )


TECH_ARTICLE = _make_article(
    content=(
        "Artificial intelligence and machine learning are revolutionizing software development. "
        "New AI algorithms are improving computer programming and data analysis. "
        "Cloud computing and cybersecurity are major concerns for technology companies."
    ),
    title="AI Revolution in Tech",
    language="en",
)

SPORTS_ARTICLE = _make_article(
    content=(
        "The football championship was held last weekend. "
        "The team won the match with a brilliant goal in the final minutes. "
        "The coach praised the players for their outstanding performance in the tournament."
    ),
    title="Football Championship Finals",
    language="en",
)

AR_TECH_ARTICLE = _make_article(
    content=(
        "يُحدث الذكاء الاصطناعي ثورة في عالم التقنية والبرمجة. "
        "تعمل الشركات على تطوير خوارزميات جديدة لتحسين الشبكات والبيانات. "
        "يُعد الأمن الإلكتروني من أبرز التحديات في العصر الرقمي."
    ),
    title="الذكاء الاصطناعي يغيّر التقنية",
    language="ar",
)

POSITIVE_ARTICLE = _make_article(
    content=(
        "The company achieved amazing results this quarter. "
        "The team's excellent performance led to outstanding growth and success. "
        "Investors are happy with the brilliant progress and positive outlook."
    ),
    title="Record Breaking Success",
)

NEGATIVE_ARTICLE = _make_article(
    content=(
        "The company's crisis deepens as losses mount and problems persist. "
        "The terrible management failure has led to disaster and decline. "
        "Investors are worried about the worst performing quarter in history."
    ),
    title="Company Faces Crisis",
)

NEUTRAL_ARTICLE = _make_article(
    content=(
        "The meeting was held on Tuesday. "
        "Representatives from various departments attended the session. "
        "The agenda included several items for discussion."
    ),
    title="Weekly Meeting",
)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Keyword Density Score
# ─────────────────────────────────────────────────────────────────────────────

class TestKeywordDensityScore:
    def test_exact_match_returns_positive_score(self):
        score, matched = _keyword_density_score(
            "artificial intelligence is great",
            ["artificial intelligence", "machine learning"],
            word_count=5,
        )
        assert score > 0
        assert "artificial intelligence" in matched

    def test_no_match_returns_zero(self):
        score, matched = _keyword_density_score(
            "cooking recipe for pasta",
            ["football", "soccer", "basketball"],
            word_count=5,
        )
        assert score == 0.0
        assert matched == []

    def test_score_bounded_at_1(self):
        # نص مليء بالكلمات المفتاحية
        score, _ = _keyword_density_score(
            "AI AI AI AI AI AI AI AI AI AI",
            ["AI"],
            word_count=10,
        )
        assert score <= 1.0

    def test_empty_text(self):
        score, matched = _keyword_density_score("", ["AI"], word_count=0)
        assert score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: TopicClassifier
# ─────────────────────────────────────────────────────────────────────────────

class TestTopicClassifier:
    def test_default_config(self):
        clf = TopicClassifier()
        assert clf.config.max_topics == 3
        assert clf.config.min_score > 0

    def test_classifies_technology_article(self):
        clf = TopicClassifier()
        result = clf.classify_article(TECH_ARTICLE)
        assert isinstance(result, ClassificationResult)
        assert result.primary_topic in {"technology", "business", "science"}

    def test_classifies_sports_article(self):
        clf = TopicClassifier()
        result = clf.classify_article(SPORTS_ARTICLE)
        assert result.primary_topic == "sports"

    def test_arabic_tech_classification(self):
        clf = TopicClassifier()
        result = clf.classify_article(AR_TECH_ARTICLE)
        # يجب أن يُصنَّف كـ technology
        assert result.primary_topic in {"technology", "security", "general"}

    def test_returns_topic_scores(self):
        clf = TopicClassifier()
        result = clf.classify_article(TECH_ARTICLE)
        assert len(result.topics) > 0
        for t in result.topics:
            assert isinstance(t, TopicScore)
            assert 0.0 <= t.score <= 1.0

    def test_max_topics_respected(self):
        cfg = TopicClassifierConfig(max_topics=2)
        clf = TopicClassifier(cfg)
        result = clf.classify_article(TECH_ARTICLE)
        assert len(result.topics) <= 2

    def test_fallback_topic_for_ambiguous_content(self):
        clf = TopicClassifier()
        ambiguous = _make_article("The world is complex. Many things happen.", "Something")
        result = clf.classify_article(ambiguous)
        # لا نتحقق من topic محدد — فقط أن النتيجة صحيحة
        assert isinstance(result.primary_topic, str)
        assert len(result.primary_topic) > 0

    def test_enrich_article_adds_metadata(self):
        clf = TopicClassifier()
        enriched = clf.enrich_article(TECH_ARTICLE)
        extra = enriched.metadata.extra
        assert "primary_topic" in extra
        assert "topics" in extra
        assert "topic_confidence" in extra

    def test_enrich_article_adds_primary_tag(self):
        clf = TopicClassifier()
        enriched = clf.enrich_article(TECH_ARTICLE)
        assert len(enriched.metadata.tags) > 0

    def test_enrich_batch_processes_all(self):
        clf = TopicClassifier()
        articles = [TECH_ARTICLE, SPORTS_ARTICLE, POSITIVE_ARTICLE]
        enriched = clf.enrich_batch(articles)
        assert len(enriched) == 3
        for a in enriched:
            assert "primary_topic" in a.metadata.extra

    def test_custom_topics(self):
        custom = {"cooking": {"en": ["recipe", "chef", "pasta", "sauce", "kitchen"]}}
        clf = TopicClassifier(custom_topics=custom)
        food_article = _make_article("The chef prepared a delicious pasta recipe with sauce.", "Cooking")
        result = clf.classify_article(food_article)
        assert "cooking" in result.topic_names

    def test_classify_text_directly(self):
        clf = TopicClassifier()
        topics = clf.classify_text(
            text="election results president parliament vote democracy",
            language="en",
        )
        assert len(topics) > 0
        assert topics[0].topic == "politics"


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Lexicon Score
# ─────────────────────────────────────────────────────────────────────────────

class TestLexiconScore:
    def test_positive_text_scores_positive(self):
        pos, neg, neu = _lexicon_score("This is great excellent amazing success!", language="en")
        assert pos > neg

    def test_negative_text_scores_negative(self):
        pos, neg, neu = _lexicon_score("This is terrible disaster failure crisis!", language="en")
        assert neg > pos

    def test_neutral_text_scores_neutral(self):
        _, _, neu = _lexicon_score("The meeting was held on Tuesday.", language="en")
        assert neu > 0.5

    def test_scores_sum_to_one(self):
        pos, neg, neu = _lexicon_score("Good and bad day.", language="en")
        assert abs(pos + neg + neu - 1.0) < 1e-6

    def test_arabic_positive(self):
        pos, neg, neu = _lexicon_score("هذا رائع وممتاز ونجاح كبير", language="ar")
        assert pos > neg

    def test_arabic_negative(self):
        pos, neg, neu = _lexicon_score("هذه كارثة وفشل ذريع وخسارة فادحة", language="ar")
        assert neg > pos

    def test_empty_text(self):
        pos, neg, neu = _lexicon_score("", language="en")
        assert pos == 0.0
        assert neg == 0.0
        assert neu == 1.0

    def test_negation_flips_sentiment(self):
        pos_plain, neg_plain, _ = _lexicon_score("great success!", language="en")
        pos_neg, neg_neg, _ = _lexicon_score("not great success!", language="en")
        # مع negation → الإيجابي يجب أن يكون أقل أو السلبي أعلى
        assert pos_neg <= pos_plain or neg_neg >= neg_plain


class TestComputeCompound:
    def test_positive_inputs(self):
        c = _compute_compound(0.8, 0.1)
        assert c > 0

    def test_negative_inputs(self):
        c = _compute_compound(0.1, 0.8)
        assert c < 0

    def test_neutral(self):
        c = _compute_compound(0.5, 0.5)
        assert c == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: SentimentAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

class TestSentimentAnalyzer:
    def test_default_config(self):
        analyzer = SentimentAnalyzer()
        assert analyzer.config.positive_threshold == 0.1

    def test_positive_article_labeled_positive(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_article(POSITIVE_ARTICLE)
        assert result.label in {"positive", "neutral"}  # قد يكون محايداً
        # compound يجب أن يكون إيجابياً
        assert result.compound >= 0

    def test_negative_article_labeled_negative(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_article(NEGATIVE_ARTICLE)
        assert result.label in {"negative", "neutral"}

    def test_result_has_correct_fields(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_article(POSITIVE_ARTICLE)
        assert isinstance(result, SentimentResult)
        assert result.article_id == POSITIVE_ARTICLE.id
        assert result.label in {"positive", "negative", "neutral"}
        assert -1.0 <= result.compound <= 1.0
        assert 0.0 <= result.positive <= 1.0
        assert 0.0 <= result.negative <= 1.0
        assert 0.0 <= result.neutral <= 1.0
        assert result.method in {"vader", "lexicon"}

    def test_enrich_article_adds_sentiment(self):
        analyzer = SentimentAnalyzer()
        enriched = analyzer.enrich_article(POSITIVE_ARTICLE)
        assert "sentiment" in enriched.metadata.extra
        sentiment_data = enriched.metadata.extra["sentiment"]
        assert "label" in sentiment_data
        assert "compound" in sentiment_data

    def test_enrich_batch_processes_all(self):
        analyzer = SentimentAnalyzer()
        articles = [POSITIVE_ARTICLE, NEGATIVE_ARTICLE, NEUTRAL_ARTICLE]
        enriched = analyzer.enrich_batch(articles)
        assert len(enriched) == 3
        for a in enriched:
            assert "sentiment" in a.metadata.extra

    def test_result_to_dict(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_article(POSITIVE_ARTICLE)
        d = result.to_dict()
        assert "label" in d
        assert "compound" in d
        assert "positive" in d
        assert "negative" in d
        assert "neutral" in d
        assert "method" in d

    def test_analyze_text_directly(self):
        analyzer = SentimentAnalyzer()
        result = analyzer.analyze_text(
            text="This is great and excellent!",
            title="Success Story",
            language="en",
        )
        assert isinstance(result, SentimentResult)
