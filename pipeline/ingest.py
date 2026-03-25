"""
Data Ingestion Module

Handles two data source modes:
    1. Live mode  — Scrapes RSS feeds from real business news sources
    2. Sample mode — Loads from local JSON/CSV files

Outputs raw data to CSV and JSON for traceability.
"""

import csv
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from pipeline.models import RawDeal

logger = logging.getLogger(__name__)


def ingest(
    source: str,
    config: dict,
    sample_path: str = "data/sample_deals.json",
) -> List[RawDeal]:
    """
    Ingest deal data from the specified source.

    Args:
        source: "live" for RSS feeds, "sample" for local JSON/CSV.
        config: Pipeline configuration dictionary.
        sample_path: Path to sample data file (JSON or CSV).

    Returns:
        List of RawDeal objects.
    """
    if source == "live":
        deals = _ingest_from_rss(config)
        if not deals:
            logger.warning("Live RSS ingestion returned no results. Falling back to sample data.")
            deals = _ingest_from_file(sample_path)
    else:
        deals = _ingest_from_file(sample_path)

    # Normalize fields
    deals = [_normalize_deal(d) for d in deals]

    logger.info(f"Ingested {len(deals)} articles from source='{source}'")
    return deals


def _ingest_from_rss(config: dict) -> List[RawDeal]:
    """Scrape deal news from configured RSS feeds."""
    try:
        import feedparser
        import requests
    except ImportError:
        logger.error("feedparser/requests not installed. Run: pip install feedparser requests")
        return []

    feeds_config = config.get("rss_feeds", {})
    timeout = feeds_config.get("request_timeout", 10)
    max_age_days = feeds_config.get("max_age_days", 14)
    cutoff_date = datetime.now() - timedelta(days=max_age_days)
    feeds = feeds_config.get("feeds", [])

    deals: List[RawDeal] = []

    for feed_info in feeds:
        feed_name = feed_info.get("name", feed_info["url"])
        feed_url = feed_info["url"]

        logger.info(f"Fetching RSS feed: {feed_name}")
        try:
            response = requests.get(feed_url, timeout=timeout)
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            skipped_old = 0
            for entry in feed.entries:
                pub_date_str = _parse_rss_date(entry.get("published", ""))
                
                # Time-bound filter (Drop old articles to save AI Tokens)
                try:
                    pub_date_obj = datetime.strptime(pub_date_str, "%Y-%m-%d")
                    if pub_date_obj < cutoff_date:
                        skipped_old += 1
                        continue
                except ValueError:
                    pass

                deal = RawDeal(
                    title=entry.get("title", ""),
                    source=_extract_source_from_rss(entry, feed_name),
                    url=entry.get("link", ""),
                    published_date=pub_date_str,
                    summary=_clean_html(entry.get("summary", entry.get("description", ""))),
                )
                deals.append(deal)

            logger.info(f"  → Got {len(feed.entries) - skipped_old} fresh entries (skipped {skipped_old} older than {max_age_days} days) from {feed_name}")

        except Exception as e:
            logger.warning(f"  → Failed to fetch {feed_name}: {e}")
            continue

    return deals


def _ingest_from_file(filepath: str) -> List[RawDeal]:
    """Load deal data from a local JSON or CSV file."""
    if not os.path.exists(filepath):
        logger.error(f"Sample data file not found: {filepath}")
        return []

    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        deals = [RawDeal.from_dict(item) for item in data]

    elif ext == ".csv":
        deals = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                deals.append(RawDeal.from_dict(row))
    else:
        logger.error(f"Unsupported file format: {ext}")
        return []

    logger.info(f"Loaded {len(deals)} articles from {filepath}")
    return deals


def save_raw_data(deals: List[RawDeal], output_dir: str) -> None:
    """Save raw ingested data to both CSV and JSON in the output directory."""
    os.makedirs(output_dir, exist_ok=True)

    # Save as JSON
    json_path = os.path.join(output_dir, "raw_deals.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([d.to_dict() for d in deals], f, indent=2, ensure_ascii=False)
    logger.info(f"Saved raw data (JSON): {json_path}")

    # Save as CSV
    csv_path = os.path.join(output_dir, "raw_deals.csv")
    if deals:
        fieldnames = list(deals[0].to_dict().keys())
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for deal in deals:
                writer.writerow(deal.to_dict())
    logger.info(f"Saved raw data (CSV): {csv_path}")


# ── Helper Functions ──────────────────────────────────────────

def _normalize_deal(deal: RawDeal) -> RawDeal:
    """Normalize fields for consistency."""
    deal.title = deal.title.strip()
    deal.source = deal.source.strip()
    deal.summary = deal.summary.strip()
    deal.deal_type = deal.deal_type.strip() if deal.deal_type else "Unknown"
    deal.sector = deal.sector.strip() if deal.sector else ""
    deal.region = deal.region.strip() if deal.region else ""

    # Normalize date to ISO format if possible
    deal.published_date = _normalize_date(deal.published_date)

    return deal


def _normalize_date(date_str: str) -> str:
    """Attempt to normalize date string to YYYY-MM-DD format."""
    date_str = date_str.strip()
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")

    # Already in YYYY-MM-DD
    if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
        return date_str

    # Try common formats
    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",   # RSS format
        "%a, %d %b %Y %H:%M:%S %z",   # RSS with timezone offset
        "%Y-%m-%dT%H:%M:%S%z",         # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",          # ISO 8601 UTC
        "%d %b %Y",                     # "20 Mar 2026"
        "%B %d, %Y",                    # "March 20, 2026"
        "%m/%d/%Y",                     # "03/20/2026"
    ]:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str  # Return as-is if parsing fails


def _extract_source_from_rss(entry: dict, feed_name: str) -> str:
    """Extract the original source name from an RSS entry."""
    # Google News includes source in the title like "... - Reuters"
    title = entry.get("title", "")
    if " - " in title:
        source = title.rsplit(" - ", 1)[-1].strip()
        if len(source) < 50:  # Sanity check
            return source

    # Try source field
    source = entry.get("source", {})
    if isinstance(source, dict):
        return source.get("title", feed_name)
    elif isinstance(source, str):
        return source

    return feed_name


def _parse_rss_date(date_str: str) -> str:
    """Parse RSS date formats to YYYY-MM-DD."""
    return _normalize_date(date_str)


def _clean_html(text: str) -> str:
    """Remove basic HTML tags from summary text."""
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"&\w+;", " ", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
