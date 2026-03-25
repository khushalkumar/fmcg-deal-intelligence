"""
Database Persistence Module (SQLite)

Provides a lightweight persistence layer for storing historical deal data
across pipeline runs. This enables:
    1. Historical trend analysis — track deal activity over months
    2. Skip re-processing    — avoid re-scoring articles already in the DB
    3. Cross-run dedup       — catch duplicates that span different pipeline runs

Uses Python's built-in sqlite3 (zero dependencies, serverless, file-based).
"""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Default database path (relative to project root)
DEFAULT_DB_PATH = "deals.db"

# ── Schema ───────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS deals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title_hash      TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    summary         TEXT,
    source          TEXT,
    published_date  TEXT,
    deal_type       TEXT,
    deal_value      TEXT,
    buyer           TEXT,
    target          TEXT,
    region          TEXT,
    relevance_score REAL,
    credibility_score REAL,
    combined_score  REAL,
    is_low_credibility INTEGER DEFAULT 0,
    url             TEXT,
    pipeline_run_date TEXT NOT NULL,
    raw_json        TEXT,
    UNIQUE(title_hash)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_title_hash ON deals(title_hash);
CREATE INDEX IF NOT EXISTS idx_pipeline_run ON deals(pipeline_run_date);
CREATE INDEX IF NOT EXISTS idx_combined_score ON deals(combined_score DESC);
"""


def _compute_hash(title: str, source: str = "") -> str:
    """Generate a consistent hash for dedup across runs."""
    normalized = f"{title.strip().lower()}|{source.strip().lower()}"
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class DealDatabase:
    """SQLite-backed persistence for deal intelligence data."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Open a connection and initialize the schema if needed."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")  # Better concurrency
        self.conn.executescript(CREATE_TABLE_SQL)
        self.conn.executescript(CREATE_INDEX_SQL)
        logger.info(f"Database connected: {self.db_path}")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ── Write Operations ─────────────────────────────────────

    def save_deals(self, scored_deals: List[Dict], run_date: Optional[str] = None) -> int:
        """
        Persist scored deals to the database.
        Uses INSERT OR IGNORE to skip duplicates silently.
        Returns the number of NEW deals inserted.
        """
        if not self.conn:
            raise RuntimeError("Database not connected. Call connect() first.")

        run_date = run_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0

        for deal in scored_deals:
            title = deal.get("title", "")
            source = deal.get("source", "")
            title_hash = _compute_hash(title, source)

            try:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO deals
                    (title_hash, title, summary, source, published_date,
                     deal_type, deal_value, buyer, target, region,
                     relevance_score, credibility_score, combined_score,
                     is_low_credibility, url, pipeline_run_date, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        title_hash,
                        title,
                        deal.get("summary", ""),
                        source,
                        deal.get("published_date", ""),
                        deal.get("deal_type", "Unknown"),
                        deal.get("deal_value", ""),
                        deal.get("buyer", ""),
                        deal.get("target", ""),
                        deal.get("region", ""),
                        deal.get("relevance_score", 0),
                        deal.get("credibility_score", 0),
                        deal.get("combined_score", 0),
                        1 if deal.get("is_low_credibility", False) else 0,
                        deal.get("url", ""),
                        run_date,
                        json.dumps(deal, default=str),
                    ),
                )
                if self.conn.total_changes > 0:
                    inserted += 1
            except sqlite3.Error as e:
                logger.warning(f"Failed to insert deal '{title[:50]}': {e}")

        self.conn.commit()
        logger.info(f"Saved {inserted} new deals to database ({len(scored_deals) - inserted} already existed)")
        return inserted

    # ── Read Operations ──────────────────────────────────────

    def get_existing_hashes(self) -> Set[str]:
        """Return all title_hashes currently in the DB (for cross-run dedup)."""
        if not self.conn:
            raise RuntimeError("Database not connected.")

        cursor = self.conn.execute("SELECT title_hash FROM deals")
        return {row["title_hash"] for row in cursor.fetchall()}

    def get_deal_count(self) -> int:
        """Return total number of deals in the database."""
        if not self.conn:
            return 0
        cursor = self.conn.execute("SELECT COUNT(*) as cnt FROM deals")
        return cursor.fetchone()["cnt"]

    def get_run_count(self) -> int:
        """Return the number of distinct pipeline runs recorded."""
        if not self.conn:
            return 0
        cursor = self.conn.execute("SELECT COUNT(DISTINCT pipeline_run_date) as cnt FROM deals")
        return cursor.fetchone()["cnt"]

    def get_all_deals(self, limit: int = 100) -> List[Dict]:
        """Return deals ordered by combined score (most recent run first)."""
        if not self.conn:
            return []
        cursor = self.conn.execute(
            """
            SELECT * FROM deals
            ORDER BY pipeline_run_date DESC, combined_score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def is_known_article(self, title: str, source: str = "") -> bool:
        """Check if we've already processed this article in a previous run."""
        if not self.conn:
            return False
        title_hash = _compute_hash(title, source)
        cursor = self.conn.execute(
            "SELECT 1 FROM deals WHERE title_hash = ?", (title_hash,)
        )
        return cursor.fetchone() is not None
