#!/usr/bin/env python3
"""
FMCG Deal Intelligence Newsletter Pipeline — Main Orchestrator

Usage:
    python main.py                           # Run with sample data (default)
    python main.py --source live             # Run with live RSS feed scraping
    python main.py --source sample           # Run with simulated dataset
    python main.py --output-dir custom_out   # Custom output directory
    python main.py --config config.yaml      # Custom config file

Pipeline stages:
    1. INGEST      → Load deal news from RSS feeds or sample data
    2. DE-DUPE     → Remove exact and near-duplicate articles
    3. RELEVANCE   → Score and filter for FMCG deal relevance
    4. CREDIBILITY → Score source credibility and flag low-quality
    5. NEWSLETTER  → Generate DOCX, Excel, and JSON outputs
"""

import argparse
import logging
import os
import sys
import time

import yaml

from pipeline.ingest import ingest, save_raw_data
from pipeline.dedup import deduplicate
from pipeline.relevance import score_relevance
from pipeline.credibility import score_credibility, get_source_scores
from pipeline.newsletter import generate_newsletter
from pipeline.models import PipelineStats


def setup_logging(verbose: bool = False) -> None:
    """Configure logging with appropriate format and level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
    )


def load_config(config_path: str) -> dict:
    """Load pipeline configuration from YAML file."""
    if not os.path.exists(config_path):
        logging.error(f"Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logging.info(f"Loaded configuration from: {config_path}")
    return config


def run_pipeline(source: str, config: dict, output_dir: str) -> None:
    """
    Execute the full pipeline: ingest → dedup → relevance → credibility → newsletter.

    Args:
        source: Data source ("live" or "sample").
        config: Pipeline configuration dictionary.
        output_dir: Directory for output files.
    """
    logger = logging.getLogger(__name__)
    stats = PipelineStats()
    start_time = time.time()

    print("\n" + "=" * 60)
    print("  FMCG DEAL INTELLIGENCE NEWSLETTER PIPELINE")
    print("=" * 60)
    print(f"  Source:     {source}")
    print(f"  Output:     {output_dir}")
    print(f"  Timestamp:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    # ── Stage 1: INGEST ──────────────────────────────────────
    print("┌─ Stage 1: INGESTION ─────────────────────────────────────")
    raw_deals = ingest(source=source, config=config)
    stats.total_ingested = len(raw_deals)

    # Save raw data
    save_raw_data(raw_deals, output_dir)
    print(f"│  ✓ Ingested {len(raw_deals)} articles")
    print(f"│  ✓ Raw data saved to {output_dir}/")
    print("└──────────────────────────────────────────────────────────\n")

    if not raw_deals:
        print("⚠ No articles ingested. Pipeline terminated.")
        return

    # ── Stage 2: DE-DUPLICATION ──────────────────────────────
    print("┌─ Stage 2: DE-DUPLICATION ────────────────────────────────")

    # Get credibility scores for dedup (to pick best source among dupes)
    source_scores = get_source_scores(config)

    deduped_deals, exact_removed, near_removed = deduplicate(
        raw_deals, config, credibility_scores=source_scores
    )
    stats.exact_duplicates_removed = exact_removed
    stats.near_duplicates_removed = near_removed
    stats.after_dedup = len(deduped_deals)

    print(f"│  ✓ Exact duplicates removed:  {exact_removed}")
    print(f"│  ✓ Near-duplicates merged:    {near_removed}")
    print(f"│  ✓ Remaining articles:        {len(deduped_deals)}")
    print("└──────────────────────────────────────────────────────────\n")

    # ── Stage 3: RELEVANCE SCORING ───────────────────────────
    print("┌─ Stage 3: RELEVANCE SCORING ─────────────────────────────")
    scored_deals, filtered_count = score_relevance(deduped_deals, config)
    stats.irrelevant_filtered = filtered_count
    stats.after_relevance = len(scored_deals)

    print(f"│  ✓ Relevant articles:         {len(scored_deals)}")
    print(f"│  ✓ Irrelevant filtered out:   {filtered_count}")
    print("└──────────────────────────────────────────────────────────\n")

    if not scored_deals:
        print("⚠ No relevant FMCG deals found. Pipeline terminated.")
        return

    # ── Stage 4: CREDIBILITY SCORING ─────────────────────────
    print("┌─ Stage 4: CREDIBILITY SCORING ───────────────────────────")
    scored_deals = score_credibility(scored_deals, config)

    low_cred = sum(1 for d in scored_deals if d.get("is_low_credibility", False))
    stats.low_credibility_flagged = low_cred
    stats.final_count = len(scored_deals)

    # Compute breakdowns
    for deal in scored_deals:
        dt = deal.get("deal_type", "Unknown")
        stats.deal_type_breakdown[dt] = stats.deal_type_breakdown.get(dt, 0) + 1
        src = deal.get("source", "Unknown")
        stats.source_breakdown[src] = stats.source_breakdown.get(src, 0) + 1

    print(f"│  ✓ Articles scored:           {len(scored_deals)}")
    print(f"│  ✓ Low-credibility flagged:   {low_cred}")
    print("└──────────────────────────────────────────────────────────\n")

    # ── Stage 5: NEWSLETTER GENERATION ───────────────────────
    print("┌─ Stage 5: NEWSLETTER GENERATION ─────────────────────────")
    stats.processing_time_seconds = round(time.time() - start_time, 2)

    generate_newsletter(
        scored_deals=scored_deals,
        stats_dict=stats.to_dict(),
        config=config,
        output_dir=output_dir,
    )

    print(f"│  ✓ newsletter.docx   — Professional Word document")
    print(f"│  ✓ newsletter.xlsx   — Excel workbook with scored data")
    print(f"│  ✓ newsletter_data.json — Web dashboard data")
    print(f"│  ✓ cleaned_deals.csv — Cleaned & scored dataset")
    print("└──────────────────────────────────────────────────────────\n")

    # ── Final Summary ────────────────────────────────────────
    print(stats.summary())

    # Print top 3 deals
    print("  TOP 3 DEALS BY COMBINED SCORE:")
    print("  " + "-" * 56)
    for i, deal in enumerate(scored_deals[:3], 1):
        print(f"  {i}. [{deal.get('combined_score', 0):.0f}] {deal.get('title', '')[:55]}")
        print(f"     {deal.get('deal_type', '')} | {deal.get('deal_value', 'Undisclosed')} | {deal.get('source', '')}")
    print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="FMCG Deal Intelligence Newsletter Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                        Run with sample data
  python main.py --source live          Scrape live RSS feeds
  python main.py --source live -v       Live mode with verbose logging
  python main.py --output-dir reports   Save to 'reports/' directory
        """,
    )
    parser.add_argument(
        "--source", "-s",
        choices=["live", "sample"],
        default=None,
        help="Data source: 'live' for RSS feeds, 'sample' for simulated data",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Output directory (default: from config.yaml or 'output')",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args()

    # Setup
    setup_logging(verbose=args.verbose)
    config = load_config(args.config)

    # Resolve parameters (CLI > config > defaults)
    pipeline_config = config.get("pipeline", {})
    source = args.source or pipeline_config.get("default_source", "sample")
    output_dir = args.output_dir or pipeline_config.get("output_dir", "output")

    # Run
    run_pipeline(source=source, config=config, output_dir=output_dir)


if __name__ == "__main__":
    main()
