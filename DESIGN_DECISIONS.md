# Design Decisions

> Every major design decision in this pipeline, with alternatives considered, trade-offs analyzed, and rationale for the chosen approach.

---

## System Design Flowchart

```
                              ┌─────────────────────────┐
                              │       config.yaml        │
                              │  (all tunable params)    │
                              └───────────┬─────────────┘
                                          │
    ┌─────────────────────────────────────┼─────────────────────────────────────┐
    │                              main.py (CLI)                                 │
    │                         argparse + logging                                │
    │                                                                           │
    │  ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌────────────┐   ┌──────┐ │
    │  │ INGEST   │──▶│ DE-DUPE  │──▶│ RELEVANCE │──▶│CREDIBILITY │──▶│NEWS- │ │
    │  │          │   │          │   │  SCORING  │   │  SCORING   │   │LETTER│ │
    │  │ RSS/JSON │   │ Hash +   │   │ GPT-5.4   │   │ Tiered     │   │ DOCX │ │
    │  │          │   │ Vectors  │   │ LLM       │   │ dictionary │   │ XLSX │ │
    │  └──────────┘   └──────────┘   └───────────┘   └────────────┘   │ JSON │ │
    │       │                                                         └──────┘ │
    │       ▼                                                            │      │
    │  raw_deals.csv                                          newsletter.docx   │
    │  raw_deals.json                                         newsletter.xlsx   │
    │                                                    newsletter_data.json   │
    │                                                       cleaned_deals.csv   │
    └───────────────────────────────────────────────────────────────────────────┘
```

---

## Decision 1: De-Duplication Method

**Chosen:** Two-Tier Semantic Deduplication (Embeddings + LLM Verification)
*(Evolved from: `difflib` → Embeddings-only → Two-Tier)*

| Approach | Pros | Cons |
|---|---|---|
| **Two-Tier: Embeddings + LLM** ✅ | Tier 1 auto-merges high-confidence matches (cosine ≥ 0.80). Tier 2 escalates borderline pairs (0.60–0.80) to an LLM judge for a YES/NO verdict. Catches edge cases that pure vector similarity misses. | Two API calls for grey-zone pairs (one embedding, one LLM). Still negligible cost (~$0.0002 per grey-zone pair). |
| **Embeddings Only** | Single API call. Fast batch processing. | Failed on the "Henkel Olaplex" edge case — cosine similarity was only 0.699 because one headline was news-style and the other was stock-market-style. |
| **difflib.SequenceMatcher** | Zero dependencies, built into Python. | Failed on the "Danone Huel" edge case. Lexical matching missed paraphrased duplicates entirely. |
| **TF-IDF + Cosine Similarity** | Weights term importance. | High-dimensional sparse vectors. Ignores word order and true semantic meaning. |

**Rationale / The Journey:**
We went through **three iterations** of de-duplication, each solving a real production failure:

1. **v1 — `difflib` (Lexical Matching):** Failed when two articles about the Danone/Huel acquisition used completely different vocabulary. Lexical similarity was below 80%.

2. **v2 — OpenAI Embeddings (Cosine Similarity ≥ 0.80):** Fixed the Danone case. But during the first live production run, we discovered a new edge case:
   * *"Germany's Henkel nears deal for hair care brand Olaplex"* (Reuters — news style)
   * *"Henkel AG stock gains on Olaplex acquisition talks"* (AD HOC NEWS — stock market style)
   * Cosine similarity: **0.699** — below the 0.80 threshold. Same deal, different framing.

3. **v3 — Two-Tier (current):** Pairs in the 0.60–0.80 "grey zone" are now escalated to a GPT-5.4 LLM call that simply answers YES or NO: *"Do these describe the same deal?"* The LLM instantly confirmed the Henkel duplicate. Cost per verification: ~$0.0002.

---

## Decision 2: Relevance Scoring

**Chosen:** GPT-5.4 LLM Classification + Structured Entity Extraction
*(Upgraded from: Weighted keyword matching)*

| Approach | Pros | Cons |
|---|---|---|
| **LLM Classification (GPT-5.4)** ✅ | Deep contextual understanding. Zero-shot: no training data. Extracts structured entities (Buyer, Target, Deal Value) in a single API call. Handles nuanced queries like "is this a strategic acquisition in the FMCG space?" | API costs (~$0.0001 per article). Latency (1-2 seconds/article). Requires internet access. |
| **Keyword Matching** | No training data needed. Fully transparent and auditable. Cost: zero. | No contextual understanding. "Apple" (fruit) vs "Apple" (company) ambiguity. Cannot extract structured entities. Requires manual keyword curation. |
| **ML Classifier** (SVM, RandomForest) | Captures non-obvious patterns. | Requires ~500+ labeled examples. Black-box. Domain-specific: needs retraining. |

**Rationale / The Journey:**
We initially implemented weighted keyword matching, which was transparent and zero-cost. However, keyword matching fundamentally cannot extract structured entities (Buyer, Target, Deal Value) from headlines — it can only classify. By upgrading to GPT-5.4, we gain both classification AND entity extraction in a single API call, while the cost per article remains negligible (~$0.0001). The LLM also eliminates false positives that keyword matching missed, such as general market outlook articles that mention FMCG terms without describing an actual deal.

---

## Decision 3: Credibility Checking

**Chosen:** Tiered source dictionary

| Approach | Pros | Cons |
|---|---|---|
| **Tiered Dictionary** ✅ | Transparent — users see exactly why a source scored 95 vs 40. Deterministic. No external dependencies or API costs. Easy to extend by adding sources to config.yaml. | Requires manual curation of source tiers. Won't score brand-new outlets automatically. Binary-ish: a source is either in the dictionary or "unknown" (40). |
| **Domain-Age Heuristics** | Automated — no manual curation. Objective metric. | Unreliable: old domains aren't necessarily credible. ".com" registration date says nothing about editorial quality. Easily gamed. |
| **Crowd-Sourced Ratings** (NewsGuard, Media Bias/Fact Check) | Professionally rated by experts. Nuanced multi-factor scoring. Widely respected. | Paid APIs ($$$). External dependency. Not all niche FMCG trade publications are rated. Coverage gaps for non-English sources. |
| **LLM-Based Credibility** | Can reason about source reputation. Can analyze article content quality, not just source name. | Research shows LLMs have documented liberal bias in credibility ratings (arXiv, 2024). Smaller models hallucinate scores. Not deterministic. High cost per query. |

**Rationale:** For a business intelligence newsletter, transparency is paramount. A user asking "why did you trust this source?" should get a simple, clear answer: "Reuters is Tier 1 with a score of 95 because it's a premier global wire service." LLM-based approaches can't provide this level of transparency and have documented bias issues.

---

## Decision 4: Newsletter Output Format

**Chosen:** DOCX + Excel

| Format | Pros | Cons |
|---|---|---|
| **DOCX + Excel** ✅ | Editable and familiar. DOCX for reading, Excel for data exploration. Exactly what the assignment requested. Universal compatibility. Professional appearance with tables and formatting. | Not suitable for email distribution. Requires MS Office or compatible viewer. |
| **HTML Email** | Rich design with visual engagement. Trackable (open rates, clicks). Responsive design for mobile. | Deliverability issues (spam filters). Rendering inconsistencies across email clients. Complex to code. Not what was requested. |
| **PDF** | Fixed layout, universal viewing. Print-ready. Security features (password protection). | Not editable by recipients. File size can be large with images. Poor responsive viewing on mobile. |
| **PPT** | Visual, presentation-ready. Good for executive briefings. | Not ideal for data-heavy content. Complex to generate programmatically. Limited text formatting. |

**Rationale:** The assignment explicitly requests "excel/word/ppt format." DOCX serves as the structured newsletter for reading. Excel provides the scored dataset for analysts who want to sort/filter/explore the deal data. We also generate JSON for the web dashboard as a bonus.

---

## Decision 5: Data Source Strategy

**Chosen:** RSS feeds + simulated fallback

| Approach | Pros | Cons |
|---|---|---|
| **RSS Feeds** ✅ | Free, no API keys. Legally clean (opt-in publishing). Structured XML (title, date, summary, link). Google News RSS aggregates thousands of sources. Single-line integration with feedparser. | Limited to title + summary (no full article body). Feed availability varies. Some publishers have deprecated RSS. |
| **Web Scraping** (BeautifulSoup, Scrapy) | Access to full article text. Any publicly accessible webpage. High customization. | Legal/ethical risks (ToS violations). Breaks when sites redesign. Per-site selector maintenance. Anti-bot protections (CAPTCHAs, IP blocking). |
| **News API** (NewsAPI.org, Aylien, GDELT) | Structured, clean data. Real-time updates. Advanced filtering and NLP enrichment. Broad coverage (90K–230K outlets). | Paid ($50–500+/month for useful tier). API key dependency. Free tiers have strict limits (100 req/day, 30-day-old articles only). Vendor lock-in. |

**Rationale:** RSS feeds give us 80% of the value of a paid News API at 0% of the cost. Google News RSS with a targeted query (`FMCG+acquisition+OR+merger`) effectively acts as a free aggregator across thousands of sources. The simulated fallback ensures the pipeline always produces output even without internet access — critical for demo/submission purposes.

---

## Decision 6: Dependency Philosophy

**Chosen:** Minimal, stdlib-first

| Approach | Pros | Cons |
|---|---|---|
| **Minimal (stdlib + 5 lightweight packages)** ✅ | Easy to install (pip install in <10 seconds). No model downloads. No GPU requirements. Portable across machines. Every line of logic is readable Python. | Less powerful NLP capabilities. Manual feature engineering (keywords). No semantic understanding. |
| **Full NLP Stack** (spaCy + NLTK) | Named Entity Recognition (auto-detect company names). POS tagging. Lemmatization. Pre-trained language models. | spaCy: 400MB model download. NLTK: 10GB corpora. Installation complexity. Harder to explain to non-technical reviewers. Overkill for keyword matching. |
| **ML/DL Stack** (scikit-learn, transformers) | State-of-the-art text classification. Transfer learning with BERT/RoBERTa. | Massive dependencies (PyTorch: 2GB+). GPU recommended. Training data required. Model versioning complexity. |

**Rationale:** This pipeline's value is in the *architecture and logic*, not in model sophistication. Using stdlib-first (`difflib`, `hashlib`, `unicodedata`) means: (1) any Python developer can read and maintain the code, (2) installation is instant, (3) there are no "it works on my machine" issues, and (4) the logic is fully transparent. The 5 external packages (python-docx, openpyxl, feedparser, requests, PyYAML) are each small, stable, and well-maintained.

---

## Decision 7: Pipeline Architecture

**Chosen:** Sequential Python script with CLI

| Approach | Pros | Cons |
|---|---|---|
| **Sequential Script** ✅ | Zero infrastructure. Single `python main.py` command. Easy to understand, debug, and test. Logging at each stage. Fast for single-run pipelines. | No built-in retry/recovery. No parallel task execution. No web UI for monitoring. Manual scheduling (cron). |
| **DAG Framework** (Airflow/Prefect) | Robust retry logic. Web UI for monitoring. Dependency management between tasks. Scheduling built-in. Scalable. | Airflow: heavy infrastructure (scheduler, webserver, workers, DB). Prefect: lighter but still requires orchestration setup. Overkill for a single 5-stage pipeline. |
| **LangChain Agent** | Dynamic decision-making via LLM. Can adapt pipeline based on content. Intelligent tool selection. | Not a data orchestration framework. No scheduling/retry. LLM API costs. Non-deterministic. Adds complexity without clear benefit for a fixed pipeline. |
| **Makefile / Shell Script** | Simple chaining of commands. Cross-platform (mostly). | No error handling. No logging. No configuration management. Difficult to test. |

**Rationale:** Our pipeline is a single, linear, deterministic flow (ingest → dedup → score → generate). There are no branching paths, no parallel tasks, no long-running processes, and no inter-stage dependencies that require a DAG. A well-structured Python script with `argparse` CLI, `logging`, and `pytest` provides all the production qualities needed: configurability, observability, testability, and reproducibility.

## Decision 8: Scheduling and Deployment

**Chosen:** GitHub Actions Cron + GitHub Pages
*(Evolved from: Python Daemon + Docker → Cloud Run → GitHub Actions)*

| Approach | Pros | Cons |
|---|---|---|
| **GitHub Actions Cron** ✅ | $0 cost. Zero infrastructure to manage. Native `GITHUB_TOKEN` eliminates credential management for pushing updated files. Built-in secrets vault for the OpenAI API key. Bi-monthly cron trigger via `.github/workflows/pipeline.yml`. | Limited to 6-hour max job runtime (ours takes ~60s). Compute is shared (acceptable for a batch job). |
| **Cloud Run Job + Cloud Scheduler** | True serverless. Zero idle compute. Fully managed by GCP. | Requires GCP account, Artifact Registry, and a GitHub PAT for pushing results back — adds credential complexity. |
| **GCE VM + Docker Daemon** | Full control over the environment. Always-on server. | Wastes resources 99.9% of the time (alive 24/7 for a job that runs 60s every 15 days). Requires OS maintenance. |
| **Apache Airflow / Prefect** | Industry standard for massive DAG orchestration. | Extreme overkill for a single-step, bi-monthly batch job. |

**Rationale / The Journey:**
We initially built a Python daemon (`scheduler.py`) wrapped in Docker with `restart: always`, which is a solid portable solution. We then explored **Google Cloud Run Jobs** for true serverless execution. However, Cloud Run cannot natively push updated files back to GitHub without storing a separate GitHub PAT — adding credential management complexity.

**GitHub Actions** eliminates this entirely: it has native write access to the repository via `GITHUB_TOKEN`, runs our pipeline in ~60 seconds, commits the updated `docs/` files, and GitHub Pages automatically redeploys the dashboard. Total cost: $0. The Dockerfile and Cloud Run deployment guide (`DEPLOYMENT.md`) remain in the repo as the documented enterprise scale-up path.

```
GitHub Actions Cron (1st & 15th of every month, 9:00 AM IST)
  └──▶ Ubuntu runner boots, installs Python deps
         └──▶ python main.py --source live
               └──▶ git push updated docs/ files
                      └──▶ GitHub Pages auto-deploys dashboard
```

## Decision 9: Cloud Cost Optimization Architecture

**Chosen:** Segregated Funnel Execution (Date-Filter Layer → Token Layer → Generative Layer)

| Process Stage | Cost per API Token | Purpose | Net Cost per Article |
|---|---|---|---|
| **1. Temporal Filter** | $0.00 (Native Python) | Drops old articles (e.g., >15 days) *before* they reach the API. | $0.00 |
| **2. Semantic Filter** | $0.02 / 1M Tokens (`text-embedding-3-small`) | Generates semantic vectors for exact-match deduplication. Very cheap token tier. | ~$0.000003 |
| **3. Generative Extraction** | $0.150 / 1M Input (`gpt-4o-mini`) | Only authentic, fresh, unique articles reach this final, relatively expensive step for Entity Extraction. | ~$0.000105 |

**Rationale:** When designing Enterprise Data Engineering pipelines, passing raw, unfiltered web scraping data directly into a generative LLM leads to uncontrolled token inflation and massive monthly bills. To proactively prevent this, our architecture utilizes a **Funnel Filtering System**:
1. Google News RS yields ~150 articles bi-monthly.
2. The hardcoded 15-day python filter safely scraps 50% for free.
3. The cheap Vector Embedding model deduplicates the rest for fractions of a penny. 
4. Therefore, only the *absolutely necessary, unique, and fresh* articles actually reach the LLM layer. 

**Total Operational Cost:** Because of establishing this rigorous Funnel Architecture, the entire completely-automated bi-monthly pipeline costs approximately **$0.01 per month** to run in production.

---

## Summary Table

| Decision | Chosen | Key Reason |
|---|---|---|
| De-duplication | Two-Tier: Embeddings + LLM | Cosine Sim for high-confidence, LLM judge for grey-zone pairs |
| Relevance Scoring | GPT-5.4 LLM Classification | Deep contextual understanding, zero-shot, structured JSON extraction |
| Credibility | Tiered source dictionary | Transparent, deterministic, no bias issues |
| Output Format | DOCX + Excel + HTML + JSON | Multi-channel: executives, analysts, and web dashboard |
| Data Source | RSS feeds + fallback | Free, no API keys, legally safe |
| Dependencies | OpenAI + lightweight stdlib | Portable, fast install, fully readable |
| Architecture | Sequential script + CLI | Zero infrastructure, sufficient for linear pipeline |
| Scheduling | GitHub Actions Cron + GitHub Pages | $0, native repo access, zero credential mgmt |
| Cost Optimization | Funnel Filter Architecture | ~$0.01/month total operational cost |
