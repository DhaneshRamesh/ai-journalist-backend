# AI Journalist Backend — Azure-Ready (FastAPI + Postgres + Alembic)

Real-time media monitoring with AI-powered summarization, sentiment analysis, risk scoring, and journalist matching.
Built for Azure App Service, PostgreSQL, Azure OpenAI (GPT-4o-mini), and FAISS journalist embeddings.

---

## Overview

This backend powers a Streamlit frontend (`1_mentions.py`) that:

* Fetches Google News RSS articles
* Scrapes full article content (not just snippets)
* Generates 2–3 bullet-point AI summaries using Azure OpenAI GPT-4o-mini
* Computes sentiment, confidence, and risk score
* Stores everything in PostgreSQL
* Supports flagging, filtering, and journalist matching
* Includes re-processing for legacy articles

---

## Architecture

```
[Google News RSS]
       ↓
[jobs/ingest_rss.py] → Stores raw Articles in DB
       ↓
[jobs/process_mentions.py] → Fetches full content → AI → Stores Mentions
       ↓
[src/api/routes.py] → /api/mentions → Streamlit UI (1_mentions.py)
```

Note: Ingestion and processing are separated. Do not run AI tasks in API threads.

---

## Quickstart (Local Development)

```bash
# Clone and setup
git clone <repo>
cd azure-ready-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy env example
cp .env.example .env
```

### `.env` (Local Only — DO NOT COMMIT)

```env
# Database
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/ai_journalist

# Azure OpenAI (GPT-4o-mini)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-06-01

# Blob Storage (for FAISS index)
AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=...
JOURNALIST_INDEX_CONTAINER=indexes
JOURNALIST_INDEX_BLOB=journalists.faiss
JOURNALIST_META_BLOB=journalists_meta.json

# Admin
ADMIN_TOKEN=1

# CORS
ALLOWED_ORIGINS=http://localhost:8501,https://your-streamlit-app.azurewebsites.net
API_PREFIX=/api
```

```bash
# Load env
export $(cat .env | xargs)

# Run migrations
alembic upgrade head

# Start API
uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Open: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Azure App Service Deployment

### App Settings (Azure Portal → Configuration)

| Name                                  | Value                                     |
| ------------------------------------- | ----------------------------------------- |
| `DATABASE_URL`                        | `postgresql+psycopg://...`                |
| `AZURE_OPENAI_ENDPOINT`               | `https://your-resource.openai.azure.com/` |
| `AZURE_OPENAI_KEY`                    | `your-key`                                |
| `AZURE_OPENAI_DEPLOYMENT`             | `gpt-4o-mini`                             |
| `AZURE_OPENAI_API_VERSION`            | `2024-06-01`                              |
| `AZURE_BLOB_CONNECTION_STRING`        | `DefaultEndpointsProtocol=...`            |
| `JOURNALIST_INDEX_CONTAINER`          | `indexes`                                 |
| `JOURNALIST_INDEX_BLOB`               | `journalists.faiss`                       |
| `JOURNALIST_META_BLOB`                | `journalists_meta.json`                   |
| `ADMIN_TOKEN`                         | `1`                                       |
| `ALLOWED_ORIGINS`                     | `https://your-frontend.azurewebsites.net` |
| `API_PREFIX`                          | `/api`                                    |
| `SCM_DO_BUILD_DURING_DEPLOYMENT`      | `1`                                       |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `1800`                                    |

### Startup Command

```
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

---

## Project Structure

```
azure-ready-backend/
├── README.md
├── requirements.txt
├── alembic.ini
├── pyproject.toml
├── .env.example
│
├── src/
│   ├── api/
│   │   ├── app.py          → FastAPI app + CORS
│   │   ├── routes.py       → /mentions, /ingest, /flag, /match, /reprocess
│   │   ├── schemas.py      → Pydantic models
│   │   └── deps.py         → DB dependency
│   │
│   ├── db/
│   │   ├── base.py         → SQLAlchemy base
│   │   ├── models.py       → Article, Mention
│   │   └── session.py      → DB session
│   │
│   ├── processing/
│   │   ├── summarizer.py   → GPT-4o-mini 2–3 bullet summary
│   │   ├── sentiment.py    → Sentiment + confidence
│   │   ├── risk_detector.py→ Risk score (0.0–1.0)
│   │   ├── matching.py     → FAISS journalist match
│   │   └── blob_faiss.py   → Load index from Blob
│   │
│   └── utils/
│       └── openai_azure.py → AzureOpenAI client wrapper
│
├── jobs/
│   ├── ingest_rss.py       → Fetch Google News → Store Articles
│   └── process_mentions.py → Scrape full content → AI → Store Mentions
│
└── alembic/
    └── versions/
        └── 0001_init.py    → Initial schema
```

---

## Key Fixes & Known Issues

| Issue                                  | Root Cause              | Fix                                                    |
| -------------------------------------- | ----------------------- | ------------------------------------------------------ |
| 1. Summary shows link instead of text  | Only stored RSS snippet | Added full article scraping via `fetch_full_content()` |
| 2. Sentiment not shown                 | RSS too short           | Use full content for sentiment                         |
| 3. Flagged articles filter not working | Missing backend filter  | Added `flagged` param in routes                        |
| 4. Old articles without summary        | Never processed         | Added `/api/reprocess`                                 |
| 5. Only few articles fetched           | RSS limits & filters    | Increased limits, added link unshortening              |
| 6. 409 Conflict during deployment      | Azure file lock         | Restart + disable package mode + Zip deploy            |

---

## Frontend Integration (`1_mentions.py`)

* Dynamic keyword search → `/api/ingest`
* Real-time filters: source, sentiment, flagged
* Flag button → `/api/flag`
* Suggest Journalist → `/api/match`
* Re-process → `/api/reprocess`
* Debug: “Show raw summary” checkbox

### Environment Variables (Frontend)

```env
backend_url=https://ai-journalist-backend-....azurewebsites.net
admin_token=1
```

---

## Database Schema

### `Article` Table

* `id` (PK)
* `title`
* `link`
* `source`
* `published_at`
* `content` (full text, optional)

### `Mention` Table

* `id` (PK)
* `article_id` (FK)
* `summary` (AI bullet points)
* `sentiment` (positive/negative/neutral)
* `sentiment_confidence` (float)
* `risk_score` (0.0–1.0)
* `flagged` (bool)
* `flag_reason` (text)
* `flagged_at` (timestamp)
* `created_at`

---

## Ingestion & Processing Jobs

### `jobs/ingest_rss.py`

* Fetch Google News RSS
* Store raw Article
* No AI processing

### `jobs/process_mentions.py`

* Read unprocessed Articles
* Scrape full content
* Run:

  * `summarizer.summarize_text()`
  * `sentiment.analyze_sentiment()`
  * `risk_detector.calculate_risk_score()`
* Create `Mention` entries

Run as Azure Container Apps Job (e.g., every 15 minutes).

---

## API Endpoints

| Method | Endpoint         | Description                |
| ------ | ---------------- | -------------------------- |
| GET    | `/api/health`    | Health check               |
| GET    | `/api/mentions`  | List mentions with filters |
| POST   | `/api/ingest`    | Trigger RSS fetch          |
| POST   | `/api/flag`      | Flag mention               |
| GET    | `/api/match`     | Suggest journalist         |
| POST   | `/api/reprocess` | Re-run AI on all articles  |

---

## Testing Commands

```bash
# 1. Ingest & Process
curl -X POST "http://localhost:8000/api/ingest?keywords=India&per_keyword_limit=5" \
  -H "x-admin-token: 1"

# 2. Check Summary
curl "http://localhost:8000/api/mentions?limit=1" | jq '.[] | {title, summary}'
```

Expected Output:

```json
{
  "summary": "- Trump plans high tariffs on India.\n- Aims to protect US manufacturing."
}
```

---

## Troubleshooting

| Issue                      | Solution                                       |
| -------------------------- | ---------------------------------------------- |
| Summary is a URL           | Check `process_mentions.py` scraping           |
| No sentiment               | Verify `AZURE_OPENAI_*` vars set               |
| Flagged filter not working | Ensure `flagged` param exists in `routes.py`   |
| 409 Conflict               | Restart + Zip Deploy                           |
| Cold start slow            | Increase `WEBSITES_CONTAINER_START_TIME_LIMIT` |

---

## Frontend Streamlit UI — Highlights

* Keyword search box
* Articles per keyword slider
* Filters: source, sentiment, flagged only
* Refresh, Demo Data, Legacy Google
* Per-card: Flag, Suggest Journalist
* Charts: Source bar, Sentiment pie, Risk histogram

---
