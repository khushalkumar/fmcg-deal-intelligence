"""
Tests for the Source Credibility Scoring Module.

Tests cover:
    - Tier 1, 2, 3 source scoring
    - Unknown source default scoring
    - Fuzzy source name matching
    - Low credibility flagging
    - Combined score calculation
"""

import pytest
from pipeline.credibility import score_credibility, build_credibility_lookup, get_source_scores


@pytest.fixture
def config():
    """Config with credibility tiers."""
    return {
        "credibility": {
            "low_credibility_threshold": 50,
            "unknown_source_score": 40,
            "tiers": {
                "tier_1": {
                    "score": 95,
                    "sources": ["reuters", "bloomberg", "financial times"],
                },
                "tier_2": {
                    "score": 82,
                    "sources": ["cnbc", "forbes", "business standard"],
                },
                "tier_3": {
                    "score": 65,
                    "sources": ["food dive", "cosmetics business"],
                },
            },
        }
    }


class TestCredibilityLookup:
    """Test credibility lookup dictionary building."""

    def test_builds_lookup(self, config):
        """Should create a lookup with all configured sources."""
        lookup = build_credibility_lookup(config)
        assert "reuters" in lookup
        assert "bloomberg" in lookup
        assert "cnbc" in lookup
        assert "food dive" in lookup

    def test_correct_scores(self, config):
        """Each tier should have the correct score."""
        lookup = build_credibility_lookup(config)
        assert lookup["reuters"][0] == 95
        assert lookup["cnbc"][0] == 82
        assert lookup["food dive"][0] == 65


class TestCredibilityScoring:
    """Test credibility scoring of deal articles."""

    def test_tier1_scoring(self, config):
        """Reuters article should get Tier 1 score."""
        deals = [{
            "title": "Test Deal", "source": "Reuters",
            "relevance_score": 80,
        }]
        result = score_credibility(deals, config)
        assert result[0]["credibility_score"] == 95
        assert result[0]["is_low_credibility"] is False

    def test_unknown_source_scoring(self, config):
        """Unknown source should get default score of 40."""
        deals = [{
            "title": "Test Deal", "source": "Random Blog",
            "relevance_score": 80,
        }]
        result = score_credibility(deals, config)
        assert result[0]["credibility_score"] == 40
        assert result[0]["is_low_credibility"] is True

    def test_low_credibility_flagging(self, config):
        """Sources below threshold should be flagged."""
        deals = [{
            "title": "Test Deal", "source": "Unknown Source",
            "relevance_score": 80,
        }]
        result = score_credibility(deals, config)
        assert result[0]["is_low_credibility"] is True

    def test_combined_score_calculation(self, config):
        """Combined score should be 60% relevance + 40% credibility."""
        deals = [{
            "title": "Test Deal", "source": "Reuters",
            "relevance_score": 80,
        }]
        result = score_credibility(deals, config)
        expected = 0.6 * 80 + 0.4 * 95  # 48 + 38 = 86
        assert result[0]["combined_score"] == expected

    def test_fuzzy_source_matching(self, config):
        """'The Financial Times' should match 'financial times'."""
        deals = [{
            "title": "Test Deal", "source": "The Financial Times",
            "relevance_score": 70,
        }]
        result = score_credibility(deals, config)
        assert result[0]["credibility_score"] == 95

    def test_get_source_scores(self, config):
        """get_source_scores should return flat dict of source → score."""
        scores = get_source_scores(config)
        assert scores["reuters"] == 95
        assert scores["cnbc"] == 82
        assert isinstance(scores, dict)
