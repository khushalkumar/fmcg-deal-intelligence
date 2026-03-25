"""
Source Credibility Scoring Module

Assigns credibility scores to articles based on their news source using a
tiered dictionary approach.

Tier System (configurable in config.yaml):
    Tier 1 (score ~95): Reuters, Bloomberg, FT, WSJ, Economic Times
    Tier 2 (score ~82): Business Standard, CNBC, Forbes, MoneyControl
    Tier 3 (score ~65): Industry blogs, trade publications
    Unknown (score 40): Unrecognized sources

Design Decision: We use a tiered dictionary instead of ML-based or LLM-based
credibility scoring because:
    - Fully transparent: users can see exactly why a source got its score
    - Deterministic: same input always produces same output
    - No bias issues (documented problem with LLM credibility ratings)
    - No external API dependencies or costs
    - Easily editable via config.yaml
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def build_credibility_lookup(config: dict) -> Dict[str, Tuple[float, str]]:
    """
    Build a lookup dictionary mapping source names to (score, tier_name).

    Args:
        config: Pipeline configuration with credibility tier definitions.

    Returns:
        Dict mapping lowercase source name → (credibility_score, tier_name)
    """
    cred_config = config.get("credibility", {})
    tiers = cred_config.get("tiers", {})
    lookup = {}

    tier_display_names = {
        "tier_1": "Tier 1 — Premier",
        "tier_2": "Tier 2 — Reputable",
        "tier_3": "Tier 3 — Niche/Regional",
    }

    for tier_key, tier_data in tiers.items():
        score = tier_data.get("score", 50)
        tier_name = tier_display_names.get(tier_key, tier_key)
        for source in tier_data.get("sources", []):
            lookup[source.lower().strip()] = (score, tier_name)

    return lookup


def score_credibility(
    scored_deals: List[Dict],
    config: dict,
) -> List[Dict]:
    """
    Enrich scored articles with credibility information.

    Args:
        scored_deals: List of deal dicts (already have relevance_score).
        config: Pipeline configuration.

    Returns:
        List of deal dicts enriched with credibility_score, credibility_tier,
        and is_low_credibility flag.
    """
    cred_config = config.get("credibility", {})
    low_threshold = cred_config.get("low_credibility_threshold", 50)
    unknown_score = cred_config.get("unknown_source_score", 40)

    lookup = build_credibility_lookup(config)

    low_cred_count = 0

    for deal in scored_deals:
        source_lower = deal.get("source", "").lower().strip()

        # Look up credibility
        if source_lower in lookup:
            cred_score, tier_name = lookup[source_lower]
        else:
            # Try partial matching (e.g., "The Economic Times" → "economic times")
            cred_score, tier_name = _fuzzy_source_match(source_lower, lookup, unknown_score)

        deal["credibility_score"] = cred_score
        deal["credibility_tier"] = tier_name
        deal["is_low_credibility"] = cred_score < low_threshold

        if deal["is_low_credibility"]:
            low_cred_count += 1
            logger.info(
                f"  ⚠ Low credibility (score={cred_score}): "
                f"[{deal['source']}] {deal['title'][:60]}"
            )

        # Compute combined score (weighted: 60% relevance + 40% credibility)
        deal["combined_score"] = round(
            0.6 * deal.get("relevance_score", 0) + 0.4 * cred_score, 1
        )

    # Sort by combined score
    scored_deals.sort(key=lambda x: x["combined_score"], reverse=True)

    logger.info(
        f"Credibility scoring: {len(scored_deals)} articles scored, "
        f"{low_cred_count} flagged as low credibility"
    )

    return scored_deals


def get_source_scores(config: dict) -> Dict[str, float]:
    """
    Get a flat dictionary of source → score for use in de-duplication.

    Returns:
        Dict mapping lowercase source name → credibility score (float)
    """
    lookup = build_credibility_lookup(config)
    return {source: score for source, (score, _) in lookup.items()}


def _fuzzy_source_match(
    source: str,
    lookup: Dict[str, Tuple[float, str]],
    default_score: float,
) -> Tuple[float, str]:
    """
    Try to match a source name against the lookup using substring matching.

    Example: "The Economic Times" should match "economic times" in the lookup.
    """
    for known_source, (score, tier) in lookup.items():
        if known_source in source or source in known_source:
            return score, tier

    return default_score, "Unknown"
