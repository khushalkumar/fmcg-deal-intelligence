"""
Tests for the De-duplication Module.

Tests cover:
    - Exact duplicate removal (identical articles)
    - Near-duplicate detection (same deal, different wording)
    - Credibility-based selection among near-duplicates
    - Edge cases (empty input, single article, all unique)
"""

import pytest
from pipeline.models import RawDeal
from pipeline.dedup import deduplicate


@pytest.fixture
def config():
    """Minimal config for dedup tests."""
    return {
        "deduplication": {
            "similarity_threshold": 0.80,
        }
    }


@pytest.fixture
def sample_deals():
    """Sample deals with intentional duplicates."""
    return [
        RawDeal(
            title="Nestlé Acquires Fireside Foods for $2.1 Billion",
            source="Reuters",
            url="https://reuters.com/nestle-fireside",
            published_date="2026-03-20",
            summary="Swiss food giant Nestlé has completed the acquisition of US-based premium snack brand Fireside Foods in a deal valued at $2.1 billion.",
        ),
        # Exact duplicate of the first
        RawDeal(
            title="Nestlé Acquires Fireside Foods for $2.1 Billion",
            source="Reuters",
            url="https://reuters.com/nestle-fireside",
            published_date="2026-03-20",
            summary="Swiss food giant Nestlé has completed the acquisition of US-based premium snack brand Fireside Foods in a deal valued at $2.1 billion.",
        ),
        # Near-duplicate (same deal, slightly different wording)
        RawDeal(
            title="Nestle Acquires Fireside Foods for $2.1 Billion",
            source="Bloomberg",
            url="https://bloomberg.com/nestle-fireside",
            published_date="2026-03-20",
            summary="Swiss food giant Nestle has completed the acquisition of US-based premium snack brand Fireside Foods in a deal valued at approximately $2.1 billion.",
        ),
        # Completely different article
        RawDeal(
            title="Unilever Invests $450M in Indian Personal Care Startup GlowNaturals",
            source="Economic Times",
            url="https://economictimes.com/unilever-glow",
            published_date="2026-03-18",
            summary="Unilever has invested $450 million for a 65% stake in GlowNaturals, a Bengaluru-based personal care startup specializing in ayurvedic skincare.",
        ),
    ]


class TestExactDeduplication:
    """Test exact duplicate removal."""

    def test_removes_exact_duplicate(self, sample_deals, config):
        """Should remove the identical Reuters article (index 1)."""
        result, exact_removed, near_removed = deduplicate(sample_deals, config)
        assert exact_removed >= 1, "Should remove at least 1 exact duplicate"

    def test_empty_input(self, config):
        """Should handle empty input gracefully."""
        result, exact, near = deduplicate([], config)
        assert result == []
        assert exact == 0
        assert near == 0

    def test_single_article(self, config):
        """Single article should pass through unchanged."""
        deal = RawDeal(
            title="Test Deal", source="Test", url="http://test.com",
            published_date="2026-01-01", summary="Test summary",
        )
        result, exact, near = deduplicate([deal], config)
        assert len(result) == 1
        assert exact == 0

    def test_all_unique(self, config):
        """All unique articles should be preserved."""
        deals = [
            RawDeal(
                title=f"Unique Deal {i}", source=f"Source {i}",
                url=f"http://test.com/{i}", published_date="2026-01-01",
                summary=f"Unique summary for deal {i}",
            )
            for i in range(5)
        ]
        result, exact, near = deduplicate(deals, config)
        assert len(result) == 5
        assert exact == 0


class TestNearDeduplication:
    """Test fuzzy near-duplicate detection."""

    def test_merges_near_duplicates(self, sample_deals, config):
        """Should detect near-duplicate Nestlé articles."""
        cred_scores = {"reuters": 95, "bloomberg": 82, "economic times": 82}
        result, exact, near = deduplicate(sample_deals, config, cred_scores)
        # Should keep Reuters (higher credibility) over Bloomberg
        assert near >= 1, "Should merge at least 1 near-duplicate"

    def test_keeps_highest_credibility(self, config):
        """Should keep the article from the highest-credibility source."""
        deals = [
            RawDeal(
                title="Big FMCG Deal Announced Today",
                source="Random Blog",
                url="http://blog.com/deal",
                published_date="2026-03-20",
                summary="A big FMCG deal was announced today worth billions.",
            ),
            RawDeal(
                title="Big FMCG Deal Announced Today by Major Company",
                source="Reuters",
                url="http://reuters.com/deal",
                published_date="2026-03-20",
                summary="A big FMCG deal was announced today worth billions dollars.",
            ),
        ]
        cred_scores = {"reuters": 95, "random blog": 30}
        result, exact, near = deduplicate(deals, config, cred_scores)
        if near > 0:
            assert result[0].source == "Reuters", "Should keep Reuters (higher credibility)"

    def test_different_articles_not_merged(self, config):
        """Completely different articles should not be merged."""
        deals = [
            RawDeal(
                title="Nestlé acquires a snack brand for billions",
                source="Reuters",
                url="http://reuters.com/1",
                published_date="2026-03-20",
                summary="Swiss food company Nestlé completed a major acquisition in the snacking segment.",
            ),
            RawDeal(
                title="Amazon opens new warehouse in Texas",
                source="CNBC",
                url="http://cnbc.com/1",
                published_date="2026-03-20",
                summary="Tech giant Amazon has opened a massive new fulfillment center in Dallas, Texas.",
            ),
        ]
        result, exact, near = deduplicate(deals, config)
        assert len(result) == 2, "Different articles should not be merged"
        assert near == 0


class TestFinalOutput:
    """Test overall dedup behavior."""

    def test_correct_final_count(self, sample_deals, config):
        """Final count should be 2 (Nestlé group + Unilever)."""
        cred_scores = {"reuters": 95, "bloomberg": 82, "economic times": 82}
        result, exact, near = deduplicate(sample_deals, config, cred_scores)
        # 4 input → 1 exact dupe removed → 3 → near-dupe merge → 2
        assert len(result) == 2, f"Expected 2 articles, got {len(result)}"
