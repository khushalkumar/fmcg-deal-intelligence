"""
De-duplication Module

Two-layer de-duplication strategy:
    1. Exact duplicate removal  — Hash-based on (normalized_title, source, date)
    2. Near-duplicate detection — OpenAI text-embedding-3-small vector embeddings
       + Cosine Similarity for semantic matching

Design Decision: We upgraded from difflib.SequenceMatcher to OpenAI embeddings
after observing edge-case failures where lexically different headlines described
the same deal event (e.g., the "Danone Huel" case). Vector embeddings understand
semantic meaning rather than character sequences, fixing these duplicates.

When near-duplicates are found, we keep the article from the highest-credibility
source (determined by credibility_score passed in or source tier lookup).
"""

import hashlib
import logging
import math
import os
import unicodedata
from typing import Dict, List, Tuple

from dotenv import load_dotenv

load_dotenv()

from pipeline.models import RawDeal, PipelineStats

logger = logging.getLogger(__name__)


def deduplicate(
    deals: List[RawDeal],
    config: dict,
    credibility_scores: Dict[str, float] = None,
) -> Tuple[List[RawDeal], int, int]:
    """
    Remove exact and near-duplicate articles.

    Args:
        deals: List of ingested RawDeal articles.
        config: Pipeline configuration (contains similarity_threshold).
        credibility_scores: Optional dict mapping source name (lowered) to score.
                           Used to pick the best article among near-dupes.

    Returns:
        Tuple of (deduplicated_deals, exact_removed_count, near_removed_count)
    """
    dedup_config = config.get("deduplication", {})
    threshold = dedup_config.get("similarity_threshold", 0.80)

    # ── Step 1: Exact Duplicate Removal ──
    unique_deals, exact_removed = _remove_exact_duplicates(deals)
    logger.info(
        f"Exact dedup: {len(deals)} → {len(unique_deals)} "
        f"({exact_removed} exact duplicates removed)"
    )

    # ── Step 2: Near-Duplicate Detection & Merging ──
    merged_deals, near_removed = _merge_near_duplicates(
        unique_deals, threshold, credibility_scores
    )
    logger.info(
        f"Fuzzy dedup: {len(unique_deals)} → {len(merged_deals)} "
        f"({near_removed} near-duplicates merged)"
    )

    return merged_deals, exact_removed, near_removed


def _remove_exact_duplicates(deals: List[RawDeal]) -> Tuple[List[RawDeal], int]:
    """
    Remove articles that are identical based on (title, source, date) hash.

    This catches cases where the same RSS feed is scraped twice or the same
    article appears multiple times in the dataset.
    """
    seen_hashes = set()
    unique = []

    for deal in deals:
        text = f"{_normalize_text(deal.title)}|{_normalize_text(deal.source)}|{deal.published_date}"
        h = hashlib.md5(text.encode("utf-8")).hexdigest()

        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(deal)

    removed = len(deals) - len(unique)
    return unique, removed


def _merge_near_duplicates(
    deals: List[RawDeal],
    threshold: float,
    credibility_scores: Dict[str, float] = None,
) -> Tuple[List[RawDeal], int]:
    """
    Detect near-duplicate articles using a two-tier strategy:
        Tier 1: Cosine Similarity >= threshold → auto-merge (high confidence)
        Tier 2: Cosine Similarity in [grey_zone, threshold) → LLM verification
    """
    if not deals:
        return deals, 0

    if credibility_scores is None:
        credibility_scores = {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY missing. Skipping semantic deduplication.")
        return deals, 0

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except ImportError:
        logger.warning("OpenAI not installed. Skipping semantic deduplication.")
        return deals, 0

    n = len(deals)
    grey_zone_threshold = 0.60  # Below this, articles are definitely different
    
    # Batch generate embeddings to save time/requests
    texts = [_normalize_text(d.title + " " + d.summary) for d in deals]
    texts = [t[:8000] if len(t) > 8000 else t for t in texts]  # Safe truncation
    
    try:
        logger.info(f"Generating semantic embeddings for {n} articles...")
        response = client.embeddings.create(input=texts, model="text-embedding-3-small")
        embeddings = [item.embedding for item in response.data]
    except Exception as e:
        logger.warning(f"Failed to generate embeddings: {e}")
        return deals, 0

    group_id = list(range(n))

    def _cosine_similarity(vec1, vec2):
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(a * a for a in vec2))
        if norm1 == 0 or norm2 == 0: return 0
        return dot / (norm1 * norm2)

    # Find near-duplicate pairs via Cosine Similarity
    grey_zone_pairs = []  # Pairs that need LLM verification
    
    for i in range(n):
        for j in range(i + 1, n):
            if _find_root(group_id, i) == _find_root(group_id, j):
                continue
            
            similarity = _cosine_similarity(embeddings[i], embeddings[j])

            if similarity >= threshold:
                # Tier 1: High confidence — auto-merge
                logger.info(
                    f"Semantic duplicate detected (similarity={similarity:.3f}):\n"
                    f"  [{deals[i].source}] {deals[i].title[:80]}\n"
                    f"  [{deals[j].source}] {deals[j].title[:80]}"
                )
                _union(group_id, i, j)
            elif similarity >= grey_zone_threshold:
                # Tier 2: Grey zone — collect for LLM verification
                grey_zone_pairs.append((i, j, similarity))
                logger.info(
                    f"Grey zone pair (similarity={similarity:.3f}) — queued for LLM check:\n"
                    f"  [{deals[i].source}] {deals[i].title[:80]}\n"
                    f"  [{deals[j].source}] {deals[j].title[:80]}"
                )

    # Tier 2: LLM verification for grey-zone pairs
    if grey_zone_pairs:
        logger.info(f"Verifying {len(grey_zone_pairs)} grey-zone pairs with LLM...")
        for i, j, sim in grey_zone_pairs:
            if _find_root(group_id, i) == _find_root(group_id, j):
                continue  # Already merged via another path
            
            is_same = _llm_verify_duplicate(client, deals[i], deals[j])
            if is_same:
                logger.info(
                    f"LLM confirmed duplicate (cosine={sim:.3f}):\n"
                    f"  [{deals[i].source}] {deals[i].title[:80]}\n"
                    f"  [{deals[j].source}] {deals[j].title[:80]}"
                )
                _union(group_id, i, j)
            else:
                logger.info(
                    f"LLM says NOT duplicate (cosine={sim:.3f}):\n"
                    f"  [{deals[i].source}] {deals[i].title[:80]}\n"
                    f"  [{deals[j].source}] {deals[j].title[:80]}"
                )

    # Collect groups
    groups: Dict[int, List[int]] = {}
    for idx in range(n):
        root = _find_root(group_id, idx)
        groups.setdefault(root, []).append(idx)

    # From each group, keep the article with the highest credibility
    kept = []
    near_removed = 0

    for root, members in groups.items():
        if len(members) == 1:
            kept.append(deals[members[0]])
        else:
            # Pick best by credibility score
            best_idx = max(
                members,
                key=lambda idx: credibility_scores.get(
                    _normalize_text(deals[idx].source), 40
                ),
            )
            kept.append(deals[best_idx])
            near_removed += len(members) - 1

            logger.info(
                f"Near-duplicate group ({len(members)} articles) → "
                f"kept [{deals[best_idx].source}] \"{deals[best_idx].title[:60]}...\""
            )

    return kept, near_removed


def _llm_verify_duplicate(client, deal_a: RawDeal, deal_b: RawDeal) -> bool:
    """
    Use LLM to verify if two articles describe the same deal/event.
    This is the final arbiter for borderline cosine similarity pairs.
    Returns True if they are duplicates.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-5.4",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial news deduplication expert. "
                        "Determine if two article headlines describe the SAME specific deal or business event. "
                        "Reply with ONLY 'YES' or 'NO'."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Article A: {deal_a.title}\n"
                        f"Source A: {deal_a.source}\n\n"
                        f"Article B: {deal_b.title}\n"
                        f"Source B: {deal_b.source}\n\n"
                        "Do these describe the SAME specific deal or business event?"
                    ),
                },
            ],
        )
        answer = response.choices[0].message.content.strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.warning(f"LLM dedup verification failed: {e}")
        return False  # Conservative: don't merge if unsure


# ── Union-Find Helpers ────────────────────────────────────────

def _find_root(group_id: list, i: int) -> int:
    """Find root of element i with path compression."""
    while group_id[i] != i:
        group_id[i] = group_id[group_id[i]]  # Path compression
        i = group_id[i]
    return i


def _union(group_id: list, i: int, j: int) -> None:
    """Union two elements."""
    root_i = _find_root(group_id, i)
    root_j = _find_root(group_id, j)
    if root_i != root_j:
        group_id[root_j] = root_i


# ── Text Utilities ────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Lowercase, strip accents, and remove extra whitespace for comparison."""
    # Decompose unicode characters and remove accent marks
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())
