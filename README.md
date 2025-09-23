# AI Journalist — Media Monitoring (MVP)

## Summary

**AI Journalist** is a media monitoring MVP that ingests news (Google News RSS), stores articles, runs lightweight NLP to:

* clean & summarize article text,
* classify sentiment (VADER),
* detect simple data-leak risk indicators (keyword heuristic),
* store results as `mentions` linked to `articles`,
* expose results via a FastAPI JSON API,
* provide scripts to ingest/process/update mentions.

This repo is intentionally modular and ready to extend (Streamlit dashboard, journalist matcher, alerts, OpenAI summariser, CI/tests).

---

## Quick status (checkpoint)

**Done**

* Ingest from Google News RSS (`scripts/ingest_once.py`).
* Articles saved to SQLite `dev.db` (`src/db/models.py` Article model).
* Processing pipeline (`scripts/process_mentions.py`) producing `mentions` with summary, sentiment, risk.
* Sentiment via `vaderSentiment` (robust; no NLTK downloads required).
* Risk detection via keyword heuristic in `src/processing/risk_detector.py`.
* Summaries cleaned (HTML stripped) in `src/processing/summarizer.py` using BeautifulSoup.
* DB models include `Article` and `Mention` (SQLAlchemy).
* API (FastAPI) exposing `/api/health` and `/api/mentions` (`src/api/app.py`, `src/api/endpoints.py`).
* Update script to refresh existing mentions in-place: `scripts/update_mentions.py`.
* `.gitignore` recommended (ignore `dev.db`, `.venv`, caches).
* Checkpoint stored (project state saved to assistant memory).

**Current live/dev data**

* `dev.db` contains imported articles and 15 mentions processed and updated.

**Left / Roadmap (recommendation order)**

1. Add Streamlit demo dashboard (`frontend/app.py`) — *quick demo* and recommended next step.
2. Journalist matcher (TF-IDF or embedding-based) using `examples/sample_journalists.csv` + `GET /api/journalists?article_id=...`.
3. Replace summarizer with LLM (OpenAI/HF) for higher-quality summaries (needs API key, caching).
4. Alerts: notify via email/Slack when `risk_score > 0` or negative sentiment.
5. Tests & CI: unit tests for ingestion + processing + API + GitHub Actions.
6. Alembic migrations for DB schema management (production readiness).
7. Social media monitoring + rate-limited ingestion + dedup across sources.
8. Journalist contact DB enrichment (profile + beats + contact method, consent & privacy checks).

---

## Repo layout (important files)

```
.
├── docs/
├── examples/                   # sample CSVs
├── frontend/                   # optional: Streamlit app (create if needed)
├── scripts/
│   ├── ingest_once.py          # fetch RSS → articles (DB or CSV)
│   ├── process_mentions.py     # create mentions from articles
│   └── update_mentions.py      # reprocess/refresh existing mentions
├── src/
│   ├── api/
│   │   ├── app.py
│   │   └── endpoints.py
│   ├── db/
│   │   └── models.py
│   ├── processing/
│   │   ├── summarizer.py
│   │   ├── sentiment.py
│   │   └── risk_detector.py
│   └── ...
├── dev.db                      # local SQLite (ignored by git)
├── requirements.txt
└── README.md
```

---

## Quickstart (local development)

Assumes you are at repo root (e.g. `/Users/you/Desktop/ai-journalist-monitor`).

1. Create & activate virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Ingest articles (one-off)

```bash
# ensures repo root is on PYTHONPATH so imports like `from src...` work
PYTHONPATH=. python3 scripts/ingest_once.py
```

4. Process mentions (create mentions from articles)

```bash
PYTHONPATH=. python3 scripts/process_mentions.py
```

5. Update mentions (recompute summaries/sentiment/risk in-place)

```bash
PYTHONPATH=. python3 scripts/update_mentions.py
```

6. Run the API (in a separate terminal)

```bash
uvicorn src.api.app:app --reload --host 127.0.0.1 --port 8000
# Health: http://127.0.0.1:8000/api/health
# Mentions: http://127.0.0.1:8000/api/mentions
```

7. (Optional) Run Streamlit UI (if you add frontend/app.py)

```bash
pip install streamlit
streamlit run frontend/app.py
# open http://localhost:8501
```

---

## Important commands (dev & git)

* Check DB counts:

```bash
sqlite3 dev.db "SELECT COUNT(*) FROM articles;"
sqlite3 dev.db "SELECT COUNT(*) FROM mentions;"
```

* Inspect latest mentions:

```bash
curl -s http://127.0.0.1:8000/api/mentions | jq .
```

* Git push to existing `develop` branch (if remote exists and branch present):

```bash
git add -A
git commit -m "Update: AI Journalist Monitor codebase"
git checkout develop
git push origin develop
```

* Create `.gitignore` (recommended)

```bash
cat > .gitignore <<'G'
dev.db
dev.db.backup
.venv/
__pycache__/
*.pyc
.DS_Store
.env
G
```

---

## Design & Implementation notes (for report)

* **Ingestion**: Google News RSS search queries with localized params; `requests` + `feedparser` parsing. We set a browser `User-Agent` to avoid simple blocks.
* **Storage**: SQLite for dev, SQLAlchemy ORM (Article & Mention models). Unique constraint on `link` prevents duplicates.
* **Processing**:

  * `summarizer.py`: BeautifulSoup to strip HTML and truncation fallback.
  * `sentiment.py`: `vaderSentiment` for compound score → Positive/Neutral/Negative.
  * `risk_detector.py`: keyword-based detection returning `risk_score` and hits.
* **API**: FastAPI endpoints returning mention objects joined with article metadata. Pydantic response models ensure stable contract.
* **Idempotency**: `process_mentions.py` checks for existing `Mention` by `article_id` and skips to avoid duplicates. `update_mentions.py` reprocesses safely in-place.

---

## Grading / Demo checklist (what to show)

1. Terminal: run `scripts/ingest_once.py` (ingest).
2. Terminal: run `scripts/process_mentions.py` (process).
3. Terminal: run `scripts/update_mentions.py` (optional refresh).
4. Terminal: run `uvicorn ...` then `curl /api/mentions` and show JSON.
5. Optional: run Streamlit dashboard and demonstrate filters + click-through.
6. Explain the design and choices (summarizer choice, sentiment, risk heuristic, dedupe logic).
7. Show tests/CI (if you add them) and next-step plans.

---

## Security & privacy notes (for report)

* Do **not** commit secrets (`.env`) or `dev.db`. Use `.env` and `.env.example` to note required credentials.
* Journalist contact data (if collected later) must be handled per privacy laws and terms of use.

---

## Checkpoint

* The assistant has stored a checkpoint of the current project state (ingest + processing + API + 15 updated mentions). When you come back, mention the checkpoint name or ask to resume from the checkpoint.

---

## Contact / next steps

If you want I can:

* write the **Streamlit demo** into `frontend/app.py` and give the run command, OR
* implement the **journalist matcher** (TF-IDF + endpoint) — high-impact feature, OR
* add **unit tests + GitHub Actions CI**.

Tell me which and I’ll produce the exact file writes and commands.
