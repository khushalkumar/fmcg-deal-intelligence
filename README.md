# FMCG Deal Intelligence Newsletter Pipeline

> An automated, AI-powered pipeline that aggregates, de-duplicates, scores, and generates a structured newsletter on M&A / investment deal activity in the FMCG sector.

**Built by:** Khushal Kumar  
**Date:** March 2026

### 🚀 Live Demo

| | Link |
|---|---|
| **📊 Dashboard** | [khushalkumar.github.io/fmcg-deal-intelligence](https://khushalkumar.github.io/fmcg-deal-intelligence) |
| **📖 HTML Newsletter** | [khushalkumar.github.io/fmcg-deal-intelligence/newsletter.html](https://khushalkumar.github.io/fmcg-deal-intelligence/newsletter.html) |

> The dashboard auto-updates every 15 days via GitHub Actions. Each run scrapes live RSS feeds, scores articles with GPT-5.4, and pushes the results to this page.

### Key Engineering Capabilities Demonstrated

| Capability | Implementation |
|---|---|
| 🔄 **Automated ETL Pipeline** | 6-stage sequential pipeline with CLI, logging, and error handling |
| 🤖 **AI-Powered Scoring & Entity Extraction** | GPT-5.4 for zero-shot FMCG deal classification + structured JSON extraction |
| 🧠 **Semantic Deduplication** | OpenAI `text-embedding-3-small` vectors + Cosine Similarity |
| 🗄️ **Database Persistence** | SQLite with cross-run deduplication and historical trend storage |
| 📊 **Live Dashboard** | Vanilla HTML/CSS/JS dashboard auto-deployed on GitHub Pages |
| ⚙️ **CI/CD Automation** | GitHub Actions bi-monthly cron job with auto-commit |
| 🐳 **Cloud Architecture** | Dockerfile + GCP Cloud Run deployment guide (`DEPLOYMENT.md`) |
| 📝 **Design Documentation** | 9 design decisions with alternatives, trade-offs, and rationale |

---

## Pipeline Architecture

```
  ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
  │    INGEST        │────▶│    DE-DUPE        │────▶│   RELEVANCE     │────▶│   CREDIBILITY    │────▶│     NEWSLETTER       │
  │                  │     │                  │     │   SCORING       │     │   SCORING        │     │     GENERATION       │
  │ • RSS feeds      │     │ • Exact hash     │     │ • GPT-5.4 LLM   │     │ • Tiered source  │     │ • DOCX (Word)        │
  │ • Sample JSON    │     │ • OpenAI Vector  │     │ • Entity extract │     │   dictionary     │     │ • XLSX (Excel)       │
  │ • 15-day filter  │     │   Embeddings     │     │ • JSON schema   │     │ • Fuzzy source   │     │ • HTML (Newsletter)  │
  │                  │     │ • Cosine Sim     │     │ • Score 0–100   │     │   matching       │     │ • JSON (Dashboard)   │
  └─────────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘     └──────────────────────┘
       ~12 articles    ──▶     ~10 unique       ──▶     ~3 relevant      ──▶     3 scored          ──▶    Final newsletter
                              (semantic dedup)         (AI filtered)           (low-cred flagged)
```

---

## Quick Start

```bash
# 1. Clone the project
git clone https://github.com/khushalkumar/fmcg-deal-intelligence.git
cd fmcg-deal-intelligence

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
fmcg-deal-intelligence/
├── main.py                    # CLI entry point — pipeline orchestrator
├── config.yaml                # All tunable parameters (feeds, LLM model, thresholds)
├── scheduler.py               # Bi-monthly Python daemon (for Docker deployment)
├── Dockerfile                 # Production container (Cloud Run / Docker)
├── .dockerignore
├── requirements.txt           # Python dependencies
├── .gitignore
├── .env.example               # Template for environment variables
│
├── .github/workflows/
│   └── pipeline.yml           # GitHub Actions bi-monthly cron job
│
├── data/
│   └── sample_deals.json      # Simulated dataset (34 entries)
│
├── pipeline/
│   ├── __init__.py
│   ├── models.py              # Dataclasses: RawDeal, ScoredDeal, PipelineStats
│   ├── ingest.py              # RSS feed scraping + JSON loading + 15-day freshness filter
│   ├── dedup.py               # Exact hash + OpenAI semantic vector deduplication
│   ├── relevance.py           # GPT-5.4 LLM relevance scoring + entity extraction
│   ├── credibility.py         # Source credibility scoring (tiered dictionary)
│   └── newsletter.py          # DOCX, Excel, HTML, JSON generation
│
├── tests/
│   ├── test_dedup.py          # 9 tests — exact/fuzzy dedup, edge cases
│   ├── test_relevance.py      # 5 tests — LLM scoring with mocked OpenAI client
│   └── test_credibility.py    # 8 tests — tier scoring, fuzzy matching
│
├── docs/                      # GitHub Pages static dashboard
│   ├── index.html             # Live dashboard (reads newsletter_data.json)
│   ├── style.css
│   ├── app.js
│   ├── newsletter.html        # Styled HTML newsletter
│   ├── newsletter_data.json   # JSON powering the dashboard
│   ├── newsletter.docx        # Downloadable Word report
│   └── newsletter.xlsx        # Downloadable Excel workbook
│
├── output/                    # Generated at runtime (gitignored)
│
├── README.md                  # This file
├── DESIGN_DECISIONS.md        # 9 design decisions with alternatives analyzed
├── ARCHITECTURE.md            # Mermaid.js system architecture diagrams
└── DEPLOYMENT.md              # Step-by-step GCP Cloud Run deployment guide
```

---

## Pipeline Stages Explained

### 1. Ingestion
- **Live mode**: Scrapes Google News RSS feeds with FMCG deal queries. No API keys needed.
- **Freshness filter**: Drops articles older than 15 days (syncs with bi-monthly cron schedule).
- **Sample mode**: Loads from `data/sample_deals.json` (34 realistic simulated entries).
- Falls back to sample data if RSS scraping fails.

### 2. De-Duplication
- **Exact removal**: MD5 hash on `(normalized_title, source, date)` — catches scraped duplicates.
- **Semantic detection**: OpenAI `text-embedding-3-small` vector embeddings + Cosine Similarity (threshold ≥ 0.80). Catches paraphrased headlines about the same deal event.
- Groups near-dupes using Union-Find and keeps the highest-credibility source.
- Unicode normalization handles accented characters (Nestlé ↔ Nestle).

### 3. Relevance Scoring
- Uses **GPT-5.4** to semantically analyze each article and determine if it describes a real FMCG deal.
- Extracts structured entities: **Buyer**, **Target**, **Deal Value**, **Deal Type** (M&A, Investment, JV, Divestiture).
- Returns a confidence score (0–100). Articles below threshold are filtered out.
- Effectively removes non-FMCG noise (tech, pharma, general market outlooks).

### 4. Credibility Scoring
- Tiered source dictionary (Tier 1: Reuters/Bloomberg = 95, Tier 2: CNBC/Forbes = 82, Tier 3: trade pubs = 65, Unknown = 40).
- Fuzzy source name matching ("The Financial Times" → matches "financial times").
- Combined score = 60% relevance + 40% credibility — used for ranking.
- Low-credibility articles (score < 50) are flagged but included with a warning.

### 5. Newsletter Generation
- **DOCX**: Executive summary, Top Deals table, deal-by-deal sections grouped by type.
- **Excel**: Full dataset with conditional formatting. Sortable/filterable.
- **HTML**: Styled newsletter viewable in any browser.
- **JSON**: Structured data powering the live web dashboard.

---

## Configuration

All parameters are editable in `config.yaml`:
- RSS feed URLs and timeout
- Freshness filter (`max_age_days: 15`)
- Semantic similarity threshold for dedup
- LLM model and system prompt
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

## Deployment

The pipeline supports multiple deployment strategies:

| Strategy | How | Cost |
|---|---|---|
| **GitHub Actions** (current) | Bi-monthly cron in `.github/workflows/pipeline.yml` → auto-commits to repo → GitHub Pages redeploys | $0 |
| **Cloud Run + Scheduler** | Dockerfile → GCP Artifact Registry → Cloud Run Job triggered by Cloud Scheduler | ~$0 (free tier) |
| **Docker on VPS** | `docker run -d --restart always` on any Linux server | ~$5/mo |

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full GCP Cloud Run step-by-step guide.

---

## Future Enhancements

1. **Database Persistence (SQLite/PostgreSQL)**: Store all historical deals to enable trend analysis and prevent re-processing across runs.
2. **Email Distribution**: Auto-send the HTML newsletter to subscribers via SendGrid/SES after each pipeline run.
3. **Advanced Dashboard Filters**: Add search by deal value range, sector sub-category, and date range.
4. **Time-Decay Scoring**: Apply a mathematical decay multiplier to penalize older deals in the final ranking.
