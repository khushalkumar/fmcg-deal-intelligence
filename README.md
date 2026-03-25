# FMCG Deal Intelligence Newsletter Pipeline

> An automated pipeline that aggregates, cleans, scores, and generates a structured newsletter on M&A / investment deal activity in the FMCG sector.

**Built by:** Khushal Kumar  
**Date:** March 2026

---

## Pipeline Architecture

```
  ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
  │    INGEST        │────▶│    DE-DUPE        │────▶│   RELEVANCE     │────▶│   CREDIBILITY    │────▶│     NEWSLETTER       │
  │                  │     │                  │     │   SCORING       │     │   SCORING        │     │     GENERATION       │
  │ • RSS feeds      │     │ • Exact hash     │     │ • FMCG keywords │     │ • Tiered source  │     │ • DOCX (Word)        │
  │ • Sample JSON    │     │ • Fuzzy match    │     │ • Deal keywords │     │   dictionary     │     │ • XLSX (Excel)       │
  │ • CSV fallback   │     │   (≥80% sim)     │     │ • Company names │     │ • Fuzzy source   │     │ • JSON (Dashboard)   │
  │                  │     │ • Union-Find     │     │ • Score 0–100   │     │   matching       │     │ • CSV (cleaned data) │
  └─────────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘     └──────────────────────┘
       34 articles    ──▶     33 unique       ──▶     24 relevant      ──▶     24 scored        ──▶    Final newsletter
                             (-1 exact dupe)         (-9 irrelevant)          (2 low-cred flagged)
```

---

## Quick Start

```bash
# 1. Clone / navigate to the project
cd Benori

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate       # macOS/Linux
# venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the pipeline (sample data)
python main.py

# 5. Run with live RSS feeds
python main.py --source live

# 6. Run tests
python -m pytest tests/ -v
```

---

## CLI Options

```
python main.py [OPTIONS]

Options:
  --source, -s    {live, sample}    Data source (default: sample)
  --output-dir, -o  DIR            Output directory (default: output/)
  --config, -c      FILE           Config file (default: config.yaml)
  --verbose, -v                    Enable debug logging
```

---

## Project Structure

```
Benori/
├── main.py                    # CLI entry point — pipeline orchestrator
├── config.yaml                # All tunable parameters
├── requirements.txt           # Python dependencies
├── .gitignore
│
├── data/
│   └── sample_deals.json      # Simulated dataset (34 entries)
│
├── pipeline/
│   ├── __init__.py
│   ├── models.py              # Dataclasses: RawDeal, ScoredDeal, PipelineStats
│   ├── ingest.py              # RSS feed scraping + JSON/CSV loading
│   ├── dedup.py               # Exact + fuzzy de-duplication
│   ├── relevance.py           # FMCG relevance scoring (keyword-based)
│   ├── credibility.py         # Source credibility scoring (tiered dictionary)
│   └── newsletter.py          # DOCX, Excel, JSON generation
│
├── tests/
│   ├── test_dedup.py          # 9 tests — exact/fuzzy dedup, edge cases
│   ├── test_relevance.py      # 5 tests — FMCG vs non-FMCG filtering
│   └── test_credibility.py    # 8 tests — tier scoring, fuzzy matching
│
├── dashboard/                 # Web dashboard (HTML/CSS/JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── output/                    # Generated at runtime
│   ├── raw_deals.csv / .json  # Raw ingested data
│   ├── cleaned_deals.csv      # After dedup + scoring
│   ├── newsletter.docx        # Professional newsletter
│   ├── newsletter.xlsx        # Excel workbook with scores
│   └── newsletter_data.json   # JSON for web dashboard
│
├── README.md                  # This file
└── DESIGN_DECISIONS.md        # All design decisions with alternatives
```

---

## Pipeline Stages Explained

### 1. Ingestion
- **Live mode**: Scrapes Google News RSS feeds with FMCG deal queries. No API keys needed.
- **Sample mode**: Loads from `data/sample_deals.json` (34 realistic simulated entries).
- Falls back to sample data if RSS scraping fails.

### 2. De-Duplication
- **Exact removal**: MD5 hash on `(normalized_title, source, date)` — catches scraped duplicates.
- **Fuzzy detection**: `difflib.SequenceMatcher` on `title + summary` with ≥80% threshold. Groups near-dupes using Union-Find and keeps the highest-credibility source.
- Unicode normalization handles accented characters (Nestlé ↔ Nestle).

### 3. Relevance Scoring
- Three weighted keyword categories: FMCG sector terms, deal-type terms, and known FMCG company names.
- Score = sum of matched keyword weights, capped at 100.
- Articles below the threshold (default: 30) are filtered out.
- Effectively removes non-FMCG noise (tech, pharma, logistics articles).

### 4. Credibility Scoring
- Tiered source dictionary (Tier 1: Reuters/Bloomberg = 95, Tier 2: CNBC/Forbes = 82, Tier 3: trade pubs = 65, Unknown = 40).
- Fuzzy source name matching ("The Financial Times" → matches "financial times").
- Combined score = 60% relevance + 40% credibility — used for ranking.
- Low-credibility articles (score < 50) are flagged but included with a warning.

### 5. Newsletter Generation
- **DOCX**: Executive summary, Top Deals table, deal-by-deal sections grouped by type (M&A, Investment, JV, Divestiture).
- **Excel**: Full dataset with conditional formatting. Sortable/filterable.
- **JSON**: Structured data for the web dashboard.

---

## Configuration

All parameters are editable in `config.yaml`:
- RSS feed URLs and timeout
- Similarity threshold for fuzzy dedup
- Relevance keywords and weights
- FMCG company list
- Source credibility tiers
- Newsletter title and formatting

---

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v

# 21 tests covering:
# - Exact and fuzzy de-duplication
# - Relevance scoring and filtering
# - Credibility tier assignment and combined scoring
# - Edge cases (empty input, unknown sources, Unicode)
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `python-docx` | DOCX newsletter generation |
| `openpyxl` | Excel workbook generation |
| `feedparser` | RSS feed parsing |
| `requests` | HTTP requests for RSS |
| `PyYAML` | Configuration file loading |
| `pytest` | Unit testing |
| `openai` | LLM inference and data extraction |
| `python-dotenv` | Environment variable management |

All dependencies are lightweight — no heavy ML frameworks needed.

---

## Production Architecture (Future Enhancements)

If this pipeline were deployed for internal business users, the following architectural upgrades would be implemented:

1. **Automated Scheduling (Cron / Airflow)**: The `main.py` pipeline would run automatically (e.g., every 12 hours) using a scheduled CRON job to continuously pull the latest intelligence.
2. **Persistent Database (SQLite / PostgreSQL)**: Ingestion data would be saved iteratively to a relational database rather than overwriting a local CSV. This allows for historical deal search on the dashboard and strictly prevents the pipeline from re-processing duplicate articles across different cron runs.
3. **Time-Bound Filtration**: To optimize OpenAI API costs, an ingestion filter would drop any RSS articles possessing a `published_date` older than a defined trailing window (e.g., `max_age_days: 14`) prior to LLM evaluation.
