# FMCG Deal Intelligence Pipeline — System Architecture
*This diagram outlines the complete end-to-end data flow, AI integration steps, and cloud deployment architecture for the automated FMCG newsletter.*

## 1. Enterprise Data Pipeline (ETL & AI Flow)

```mermaid
flowchart TD
    %% Define Styling
    classDef extract fill:#fef3c7,stroke:#d97706,stroke-width:2px;
    classDef filter fill:#fee2e2,stroke:#dc2626,stroke-width:2px;
    classDef ai fill:#ede9fe,stroke:#7c3aed,stroke-width:2px;
    classDef output fill:#d1fae5,stroke:#059669,stroke-width:2px;
    classDef server fill:#f8fafc,stroke:#475569,stroke-dasharray: 5 5;

    %% Data Sources
    subgraph Data Sources
        RSS1[Google News RSS: FMCG M&A]
        RSS2[Google News RSS: Consumer Goods]
        RSS3[Google News RSS: Food & Bev]
    end

    %% The Server
    subgraph Docker Container (Always-on Server)
        Cron((Bi-Monthly<br>Python<br>Scheduler)) -.-> |Triggers every<br>15 Days| Pipeline

        subgraph Pipeline [Python Data Pipeline]
            %% Ingestion & Fast Filters
            Ingest[📥 1. Ingestion Phase<br>Downloads ~150 articles]:::extract
            TimeFilter{⏱ 2. Temporal Filter<br>Age < 15 Days?}:::filter
            
            %% AI Deduplication
            VectorAI[🧠 3a. Vector Embedding<br>text-embedding-3-small]:::ai
            Cosine{📐 3b. Cosine Similarity<br>Semantic Threshold > 0.8}:::filter
            
            %% AI Generative Extraction
            GenAI[🤖 4. Entity Extraction<br>GPT-5.4 / gpt-4o-mini]:::ai
            ExtractJSON[📝 Extracted Schema:<br>- Buyer, Target<br>- Deal Value, Deal Type<br>- Confidence Score]:::extract
            
            %% Credibility
            Cred[🛡 5. Source Credibility<br>Publisher Tier Scoring]:::extract
            Math[🧮 6. Final Combined Score<br>60% AI Relevance + 40% Tier]:::extract
            
            %% The logic flow
            Ingest --> TimeFilter
            TimeFilter -- Yes --> VectorAI
            TimeFilter -. No (Dropped) .-> Trash1([Discarded])
            
            VectorAI --> Cosine
            Cosine -- Unique --> GenAI
            Cosine -. Duplicate .-> Trash2([Merged])
            
            GenAI --> ExtractJSON --> Cred --> Math
        end
        
        %% File Generation
        subgraph File Generation
            Math --> DOCX[📄 newsletter.docx]:::output
            Math --> XLSX[📊 newsletter.xlsx]:::output
            Math --> HTML[🌐 newsletter.html]:::output
            Math --> JSON[💻 newsletter_data.json]:::output
        end
    end

    %% Web Deployment
    subgraph Web Deployment (Static Hosting)
        Netlify[Netlify / GitHub Pages]
        HTML --> |Rendered View| Netlify
        JSON --> |Powers Dashboard| Netlify
    end

    %% Connection
    Data Sources --> Ingest
```

## 2. Cost & Efficiency Funnel
*A critical design choice was structuring the filters mathematically to minimize LLM token usage.*

```mermaid
funnel
    title Article Survival Rate per 15-Day Sprint
    "1. Raw Ingestion (RSS)" : 150
    "2. Temporal Cutoff (< 15 Days)" : 75
    "3. Semantic Deduplication (Vectors)" : 60
    "4. AI Relevance Filter (GPT)" : 20
    "5. Final Top Deals (Dashboard)" : 5
```

## Presentation Talking Points:
1. **The Process Manager:** Highlight that Docker acts as a self-healing process manager for the `scheduler.py` daemon, keeping the bi-monthly runs autonomous and insulated from host-OS crashes.
2. **The Funnel Methodology (Cost Savings):** By performing Temporal (Date) filtering for free in Python *before* passing articles to the API, and deduplicating using ultra-cheap Vector Embeddings ($0.02 / 1M tokens) *before* the expensive Generative LLM layer, the total monthly cost to run the pipeline is practically zero ($0.01).
3. **Lexical vs Semantic Deduplication:** Emphasize the pivot from Python's standard `difflib` (character matching) to OpenAI Vector Embeddings (meaning matching), demonstrating your ability to solve edge cases where journalists rewrite headlines completely differently for the exact same M&A event.
