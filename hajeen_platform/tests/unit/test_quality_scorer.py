"""Tests for section 5.6 — Quality Scorer."""

import pytest

from data_engine.processing.filtering.quality_scorer import (
    QualityScore,
    QualityScorer,
    QualityScorerConfig,
    score_content_length,
    score_link_density,
    score_metadata,
    score_readability,
    score_repetition,
    score_word_count,
)
from shared.schemas.article import Article, ArticleMetadata
from shared.utils.id_generator import generate_article_id
from shared.utils.datetime_utils import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(
    title: str = "Test Article",
    content: str = "Placeholder content.",
    author: str = "",
    tags: list | None = None,
    summary: str = "",
    url: str = "https://example.com/1",
) -> Article:
    safe_content = content if content.strip() else "Placeholder content."
    return Article(
        id=generate_article_id(title + url),
        title=title,
        content=safe_content,
        url=url,
        published_at=utc_now(),
        metadata=ArticleMetadata(
            source_id="test",
            author=author or None,
            tags=tags or [],
            language="en",
        ),
        summary=summary or None,
    )


GOOD_CONTENT = (
    "Artificial intelligence has transformed the way we process information. "
    "Machine learning algorithms can now understand natural language with remarkable accuracy. "
    "Researchers continue to push boundaries in areas like computer vision and speech recognition. "
    "These advances have practical applications in healthcare, finance, and transportation. "
    "The field continues to evolve rapidly with new discoveries every year."
)

SPAM_CONTENT = " ".join(["buy now click here" for _ in range(30)])

SHORT_CONTENT = "Short."

LINK_HEAVY = " ".join([
    "https://example.com/link" + str(i) for i in range(50)
]) + " Some actual text here."

REPETITIVE_CONTENT = " ".join(["the cat sat on the mat" for _ in range(20)])


# ---------------------------------------------------------------------------
# score_content_length
# ---------------------------------------------------------------------------

class TestScoreContentLength:
    def test_empty_content_zero(self):
        assert score_content_length("") == 0.0

    def test_below_minimum_zero(self):
        assert score_content_length("Hi", min_chars=50) == 0.0

    def test_long_content_approaches_one(self):
        score = score_content_length("A" * 2000)
        assert score >= 0.99

    def test_medium_content_partial(self):
        score = score_content_length("A" * 200)
        assert 0 < score < 1

    def test_range(self):
        for length in [0, 10, 100, 500, 2000, 5000]:
            score = score_content_length("A" * length)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# score_word_count
# ---------------------------------------------------------------------------

class TestScoreWordCount:
    def test_empty_zero(self):
        assert score_word_count("") == 0.0

    def test_below_minimum_zero(self):
        assert score_word_count("hello world", min_words=20) == 0.0

    def test_many_words_high_score(self):
        text = " ".join(["word"] * 300)
        assert score_word_count(text) >= 0.99

    def test_moderate_words(self):
        text = " ".join(["word"] * 50)
        score = score_word_count(text)
        assert 0 < score <= 1.0


# ---------------------------------------------------------------------------
# score_link_density
# ---------------------------------------------------------------------------

class TestScoreLinkDensity:
    def test_no_links_high_score(self):
        assert score_link_density("Clean text with no links.") == 1.0

    def test_empty_text(self):
        assert score_link_density("") == 1.0

    def test_link_heavy_low_score(self):
        score = score_link_density(LINK_HEAVY)
        assert score < 0.5

    def test_mixed_text_medium(self):
        text = "Visit https://example.com for more info about our products."
        score = score_link_density(text)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# score_repetition
# ---------------------------------------------------------------------------

class TestScoreRepetition:
    def test_unique_content_high_score(self):
        score = score_repetition(GOOD_CONTENT)
        assert score > 0.3

    def test_repetitive_content_low_score(self):
        score = score_repetition(REPETITIVE_CONTENT)
        assert score < 0.5

    def test_very_short_content(self):
        score = score_repetition("hi")
        assert score == 1.0

    def test_range(self):
        score = score_repetition(GOOD_CONTENT)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# score_readability
# ---------------------------------------------------------------------------

class TestScoreReadability:
    def test_empty_text(self):
        score = score_readability("")
        assert score == 0.5

    def test_short_sentences_high_score(self):
        text = "This is short. This too. And this."
        score = score_readability(text)
        assert score > 0.5

    def test_very_long_sentences_low_score(self):
        long_sentence = "A" * 300 + ". " + "B" * 300 + "."
        score = score_readability(long_sentence, max_avg_len=200)
        assert score == 0.0

    def test_range(self):
        score = score_readability(GOOD_CONTENT)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# score_metadata
# ---------------------------------------------------------------------------

class TestScoreMetadata:
    def test_full_metadata_high_score(self):
        article = make_article(
            author="John Doe",
            tags=["ai", "tech"],
            summary="A great summary.",
        )
        score = score_metadata(article)
        assert score >= 0.8

    def test_no_metadata_zero(self):
        article = make_article()
        score = score_metadata(article)
        assert score <= 0.2  # only language may count

    def test_partial_metadata(self):
        article = make_article(author="Jane Doe")
        score = score_metadata(article)
        assert score >= 0.2


# ---------------------------------------------------------------------------
# QualityScorer
# ---------------------------------------------------------------------------

class TestQualityScorer:
    def test_good_article_passes(self):
        article = make_article(
            title="AI Breakthrough",
            content=GOOD_CONTENT,
            author="Researcher",
            tags=["ai"],
            summary="Summary of the article.",
        )
        scorer = QualityScorer()
        score = scorer.score_article(article)
        assert score.passes is True
        assert score.total_score > 0.4

    def test_empty_content_fails(self):
        """Single char content should fail (word count + length both zero-score)."""
        article = make_article(title="Empty", content="x")
        scorer = QualityScorer(config=QualityScorerConfig(threshold=0.5))
        score = scorer.score_article(article)
        assert score.passes is False

    def test_short_content_fails(self):
        article = make_article(content=SHORT_CONTENT)
        scorer = QualityScorer(config=QualityScorerConfig(threshold=0.5))
        score = scorer.score_article(article)
        assert score.passes is False

    def test_link_heavy_may_fail(self):
        article = make_article(content=LINK_HEAVY)
        scorer = QualityScorer()
        score = scorer.score_article(article)
        assert isinstance(score.passes, bool)

    def test_score_has_all_dimensions(self):
        article = make_article(content=GOOD_CONTENT)
        scorer = QualityScorer()
        score = scorer.score_article(article)
        expected_dims = {"content_length", "word_count", "link_density",
                         "repetition", "readability", "metadata"}
        assert expected_dims.issubset(score.dimension_scores.keys())

    def test_rejection_reason_set_on_failure(self):
        article = make_article(content="x")
        scorer = QualityScorer(config=QualityScorerConfig(threshold=0.9))
        score = scorer.score_article(article)
        assert score.rejection_reason is not None

    def test_quality_score_type(self):
        article = make_article(content=GOOD_CONTENT)
        scorer = QualityScorer()
        score = scorer.score_article(article)
        assert isinstance(score, QualityScore)

    def test_filter_batch(self):
        articles = [
            make_article("Good", GOOD_CONTENT, url="https://x.com/1"),
            make_article("Empty", "", url="https://x.com/2"),
        ]
        scorer = QualityScorer()
        kept, all_scores = scorer.filter_batch(articles)
        assert len(all_scores) == 2
        assert len(kept) >= 1  # at least the good one passes

    def test_score_batch(self):
        articles = [
            make_article("A", GOOD_CONTENT, url="https://x.com/1"),
            make_article("B", SHORT_CONTENT, url="https://x.com/2"),
        ]
        scorer = QualityScorer()
        scores = scorer.score_batch(articles)
        assert len(scores) == 2

    def test_custom_threshold(self):
        cfg = QualityScorerConfig(threshold=0.0)
        article = make_article(content=SHORT_CONTENT)
        scorer = QualityScorer(config=cfg)
        score = scorer.score_article(article)
        assert score.passes is True  # threshold=0 → always pass

    def test_arabic_content_scored(self):
        arabic_content = (
            "أعلن فريق من الباحثين عن اكتشاف مهم في مجال الذكاء الاصطناعي "
            "يمكن أن يغير طريقة معالجة النصوص العربية بشكل جذري وسريع. "
            "الدراسة استغرقت ثلاث سنوات من العمل المتواصل والتجارب المكثفة."
        )
        article = make_article("اكتشاف", arabic_content)
        scorer = QualityScorer()
        score = scorer.score_article(article)
        assert score.total_score > 0
        assert 0.0 <= score.total_score <= 1.0
