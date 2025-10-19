# AI Journalist Backend — Azure-Ready (FastAPI + Postgres + Alembic)

This is a clean, production-lean backend for media monitoring:
- FastAPI API (health, mentions, articles, summarize, match)
- SQLAlchemy + Alembic (PostgreSQL on Azure)
- Processing modules (summarizer, sentiment, risk)
- FAISS journalist index loader from Azure Blob
- Ingestion job scripts (to run as Azure Container Apps Job / Functions / WebJob)
- Clean env config; no heavy tasks in web process

## Quickstart (local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set envs (or create .env)
export DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname"
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com"
export AZURE_OPENAI_KEY="<key>"
export AZURE_OPENAI_API_VERSION="2024-06-01"
export AZURE_BLOB_CONNECTION_STRING="<blob-conn-str>"
export JOURNALIST_INDEX_CONTAINER="indexes"
export JOURNALIST_INDEX_BLOB="journalists.faiss"
export JOURNALIST_META_BLOB="journalists_meta.json"

# DB migrate
alembic upgrade head

# Run API
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

## Azure App Service settings
- **Startup Command:** `uvicorn src.api.app:app --host 0.0.0.0 --port 8000`
- **App Settings:** set the env vars above (and remove any `.env` in prod)
- **WEBSITES_CONTAINER_START_TIME_LIMIT:** 1800 (FAISS load can be slow on cold start)
- (Optional) **PYTHONPATH:** `.`

## Jobs (ingestion / processing)
Run these as **Container Apps Jobs** or **Azure Functions** (timer trigger). They write to the same DB and (optionally) blob storage.
Do **not** run them inside API threads in production.

- `jobs/ingest_rss.py`: fetch Google News RSS and store Articles
- `jobs/process_mentions.py`: compute sentiment/risk/summaries and create Mentions

## Project layout

```
azure-ready-backend/
  README.md
  requirements.txt
  alembic.ini
  pyproject.toml
  .env.example
  src/
    api/
      app.py
      routes.py
      schemas.py
      deps.py
    db/
      base.py
      models.py
      session.py
    processing/
      summarizer.py
      sentiment.py
      risk_detector.py
      matching.py
      blob_faiss.py
    utils/
      openai_azure.py
  jobs/
    ingest_rss.py
    process_mentions.py
  alembic/
    env.py
    versions/
      0001_init.py
```
