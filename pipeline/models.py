"""
Data models for the FMCG Deal Intelligence Pipeline.

Uses Python dataclasses for type-safe data flow through the pipeline stages:
    RawDeal     → Ingested article data
    ScoredDeal  → Article with relevance + credibility scores
    PipelineStats → Counts and metrics at each pipeline stage
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime


@dataclass
class RawDeal:
    """Represents a single deal-related news article as ingested."""
    title: str
    source: str
    url: str
    published_date: str
    summary: str
    deal_type: str = "Unknown"        # M&A, Investment, JV, Divestiture, Unknown
    deal_value: str = ""              # e.g., "$2.1B", "₹500 Cr", "Undisclosed"
    buyer: str = ""
    target: str = ""
    sector: str = ""                  # Sub-sector within FMCG
    region: str = ""                  # Geographic region

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RawDeal":
        """Create RawDeal from a dictionary."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class ScoredDeal:
    """A deal article enriched with relevance and credibility scores."""
    # Original fields
    title: str
    source: str
    url: str
    published_date: str
    summary: str
    deal_type: str = "Unknown"
    deal_value: str = ""
    buyer: str = ""
    target: str = ""
    sector: str = ""
    region: str = ""

    # Scoring fields (added by pipeline)
    relevance_score: float = 0.0       # 0–100
    credibility_score: float = 0.0     # 0–100
    credibility_tier: str = "Unknown"  # Tier 1, Tier 2, Tier 3, Unknown
    is_low_credibility: bool = False
    combined_score: float = 0.0        # Weighted average for ranking
    duplicate_group_id: Optional[int] = None  # Group ID for near-dupes

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_raw_deal(cls, raw: RawDeal) -> "ScoredDeal":
        """Create ScoredDeal from a RawDeal, copying all base fields."""
        return cls(
            title=raw.title,
            source=raw.source,
            url=raw.url,
            published_date=raw.published_date,
            summary=raw.summary,
            deal_type=raw.deal_type,
            deal_value=raw.deal_value,
            buyer=raw.buyer,
            target=raw.target,
            sector=raw.sector,
            region=raw.region,
        )


@dataclass
class PipelineStats:
    """Tracks metrics at each stage of the pipeline for transparency."""
    total_ingested: int = 0
    exact_duplicates_removed: int = 0
    near_duplicates_removed: int = 0
    after_dedup: int = 0
    irrelevant_filtered: int = 0
    after_relevance: int = 0
    low_credibility_flagged: int = 0
    final_count: int = 0
    source_breakdown: dict = field(default_factory=dict)
    deal_type_breakdown: dict = field(default_factory=dict)
    processing_time_seconds: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def summary(self) -> str:
        """Human-readable pipeline summary."""
        return (
            f"\n{'='*60}\n"
            f"  PIPELINE SUMMARY\n"
            f"{'='*60}\n"
            f"  Articles ingested:          {self.total_ingested}\n"
            f"  Exact duplicates removed:   {self.exact_duplicates_removed}\n"
            f"  Near-duplicates merged:      {self.near_duplicates_removed}\n"
            f"  After de-duplication:        {self.after_dedup}\n"
            f"  Irrelevant articles removed: {self.irrelevant_filtered}\n"
            f"  After relevance filter:      {self.after_relevance}\n"
            f"  Low-credibility flagged:     {self.low_credibility_flagged}\n"
            f"  Final newsletter articles:   {self.final_count}\n"
            f"  Processing time:             {self.processing_time_seconds:.2f}s\n"
            f"{'='*60}\n"
        )
