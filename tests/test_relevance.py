"""
Tests for the Relevance Scoring Module (LLM Enhanced).

Tests cover:
    - High-relevance FMCG deal articles get parsed and mapped correctly
    - Non-FMCG articles (tech, pharma) are rejected by the LLM
    - Correct mocked responses over the OpenAI client
"""

import pytest
import os
import json
from unittest.mock import patch, MagicMock
from pipeline.models import RawDeal
from pipeline.relevance import score_relevance

@pytest.fixture
def config():
    """Config with LLM settings."""
    return {
        "llm": {
            "model": "gpt-5.4",
            "system_prompt": "Mock prompt"
        },
        "relevance": {
            "min_score": 50
        }
    }


class TestRelevanceScoring:
    """Test relevance score and entity extraction computation."""

    @patch('pipeline.relevance.OpenAI')
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    def test_fmcg_deal_scores_high(self, mock_openai_class, config):
        """A clear FMCG M&A article should be accepted and parsed."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock the API JSON response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "is_fmcg_deal": True,
            "confidence_score": 95,
            "buyer": "Nestle",
            "target": "SnackCo",
            "deal_value": "$2B",
            "deal_type": "M&A"
        })
        mock_client.chat.completions.create.return_value = mock_response

        deals = [
            RawDeal(
                title="Nestlé Acquires Snack Brand",
                source="Reuters",
                url="http://test.com",
                published_date="2026-03-20",
                summary="Swiss food giant Nestlé completes acquisition."
            )
        ]
        
        scored, filtered = score_relevance(deals, config)
        
        assert len(scored) == 1
        assert scored[0]["relevance_score"] == 95
        assert scored[0]["buyer"] == "Nestle"
        assert scored[0]["target"] == "SnackCo"
        assert filtered == 0

    @patch('pipeline.relevance.OpenAI')
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"})
    def test_tech_article_filtered(self, mock_openai_class, config):
        """A tech article rejected by the LLM should be filtered."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "is_fmcg_deal": False,
            "confidence_score": 10
        })
        mock_client.chat.completions.create.return_value = mock_response

        deals = [
            RawDeal(
                title="Microsoft Cloud",
                source="TechCrunch",
                url="",
                published_date="",
                summary=""
            )
        ]
        
        scored, filtered = score_relevance(deals, config)
        assert len(scored) == 0
        assert filtered == 1
