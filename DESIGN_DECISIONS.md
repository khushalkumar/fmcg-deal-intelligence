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
    │  │ RSS/JSON │   │ Hash +   │   │ Keyword   │   │ Tiered     │   │ DOCX │ │
    │  │          │   │ difflib  │   │ matching  │   │ dictionary │   │ XLSX │ │
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

**Chosen:** `OpenAI Semantic Vector Embeddings (text-embedding-3-small)` + `Cosine Similarity`
*(Upgraded from `difflib` Lexical Matching)*

| Approach | Pros | Cons |
|---|---|---|
| **Semantic Embeddings** ✅ | Deep semantic understanding — catches paraphrases and completely differently-worded headlines about the exact same event. | Requires OpenAI API. Extremely low cost (`$0.02` per 1 million tokens), but still a non-zero dependency. |
| **difflib.SequenceMatcher** | Zero dependencies, built into Python. Fully transparent. | Failed on the "Danone Huel" edge-case. Lexical scanning missed the duplicate because the journalists used different vocabulary sizes for the exact same event. |
| **TF-IDF + Cosine Similarity** | Weights term importance. | High-dimensional sparse vectors. Still ignores word order and true semantic meaning. |

**Rationale / The Journey:** 
We originally implemented Python's built-in `difflib` lexical matcher to save costs and dependencies. However, during live testing, we observed a critical edge-case failure:
* Article 1: *"Danone announces $1.6bn acquisition of nutrition drink Huel"*
* Article 2: *"Danone Grows into Functional Nutrition with Huel Acquisition"*

Even though these articles described the exact same FMCG deal, their character structures were too distinct, yielding a lexical similarity score below 80%. This caused duplicates to slip into the newsletter.
We immediately pivoted to generating a single batch of OpenAI `text-embedding-3-small` vector embeddings for the articles and mathematically calculating their Cosine Similarity. Because vector embeddings understand *semantic meaning* rather than *character spelling*, the two articles mathematically align natively, fixing the duplicate bug instantly for fractions of a penny.

---

## Decision 2: Relevance Scoring

**Chosen:** Weighted keyword matching

| Approach | Pros | Cons |
|---|---|---|
| **Keyword Matching** ✅ | No training data needed. Fully transparent and auditable — score breakdown shows exactly why each article passed/failed. Easy to modify (edit config.yaml). Cost: zero. | No contextual understanding. "Apple" (fruit) vs "Apple" (company) ambiguity. Requires manual keyword curation. May miss novel FMCG terms. |
| **ML Classifier** (SVM, RandomForest) | Captures non-obvious patterns. High accuracy when trained on sufficient labeled data. Handles feature interactions. | Requires ~500+ labeled examples for training. Feature engineering needed. Black-box: hard to explain why an article scored 78 vs 82. Domain-specific: needs retraining for different sectors. |
| **LLM Classification** (GPT, Claude) | Deep contextual understanding. Zero-shot: no training data. Can handle nuanced queries like "is this a strategic acquisition in the FMCG space?" | API costs ($0.01-0.10 per article). Latency (1-5 seconds/article vs milliseconds). Hallucination risk — may confidently misclassify. Not deterministic. Requires internet access. |

**Rationale:** FMCG is a well-defined sector with a finite vocabulary (food, beverage, personal care, household goods). The keywords are predictable and enumerable. This makes keyword matching sufficient *and* superior to ML/LLM for this specific use case because: (1) it's deterministic, (2) it's explainable to a non-technical business user, (3) it has zero latency and zero cost, and (4) it can be maintained by anyone editing a YAML file, not just an ML engineer.

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

**Chosen:** Google Cloud Run Job + Cloud Scheduler (Serverless)
*(Evolved from: Python Daemon + Docker → Cloud Run Serverless)*

| Approach | Pros | Cons |
|---|---|---|
| **Cloud Run Job + Cloud Scheduler** ✅ | True serverless — container boots for ~60s, runs pipeline, shuts down. Zero idle compute. Fully managed by Google (no OS patching, no SSH, no Docker daemon management). Free tier covers 360K GB-seconds/month. | Requires GCP account. Slight cold-start latency (acceptable for a batch job). |
| **GCE VM + Docker Daemon** | Full control over the environment. Always-on server. | Wastes resources 99.9% of the time (alive 24/7 for a job that runs 60s every 15 days). Requires OS maintenance, SSH access, Docker updates. |
| **GitHub Actions Cron** | $0, zero infrastructure. | Limited to 6-hour max job runtime. Secrets management less secure than GCP. Not a "real" cloud deployment. |
| **Apache Airflow / Prefect** | Industry standard for massive DAG orchestration. | Extreme overkill for a single-step, bi-monthly batch job. |

**Rationale / The Journey:**
We initially built a Python daemon (`scheduler.py`) wrapped in Docker with `restart: always`, which is a solid portable solution. However, keeping a container (or VM) alive 24/7 just to execute a 60-second job every 15 days is architecturally wasteful. 

By migrating to **Google Cloud Run Jobs** triggered by **Cloud Scheduler**, the container only exists for the ~60 seconds it takes to run the pipeline. Google handles all process management, restarts, and infrastructure. The Dockerfile stays in the repo as the deployment artifact — Cloud Run simply builds and runs it on demand.

```
Cloud Scheduler (every 15 days)
  └──▶ Cloud Run Job (boots Docker container)
         └──▶ python main.py --source live
               └──▶ git push updated dashboard files
                      └──▶ GitHub Pages auto-deploys
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
| De-duplication | Semantic Vector Embeddings | Catches paraphrased duplicates that lexical matching misses |
| Relevance Scoring | GPT-5.4 LLM Classification | Deep contextual understanding, zero-shot, structured JSON extraction |
| Credibility | Tiered source dictionary | Transparent, deterministic, no bias issues |
| Output Format | DOCX + Excel + HTML + JSON | Multi-channel: executives, analysts, and web dashboard |
| Data Source | RSS feeds + fallback | Free, no API keys, legally safe |
| Dependencies | OpenAI + lightweight stdlib | Portable, fast install, fully readable |
| Architecture | Sequential script + CLI | Zero infrastructure, sufficient for linear pipeline |
| Scheduling | Cloud Run Job + Cloud Scheduler | True serverless, zero idle compute, fully managed |
| Cost Optimization | Funnel Filter Architecture | ~$0.01/month total operational cost |
