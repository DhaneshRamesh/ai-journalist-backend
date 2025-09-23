# 📰 AI Journalist Monitor

AI-powered pipeline to monitor media mentions, analyze sentiment/risk, and provide summaries — with both a FastAPI backend and a Streamlit dashboard frontend.

---

## 🚀 Features

* **Backend (FastAPI)**

  * Ingests and stores mentions/articles
  * Sentiment analysis & risk detection
  * Summarization of long texts
  * REST API for mentions, health check, etc.
* **Frontend (Streamlit)**

  * Lists mentions in a simple dashboard
  * Shows title, summary, sentiment, risk score
  * Buttons for future actions (flagging, suggesting journalists)
* **Scripts**

  * `process_mentions.py` → fetch & store mentions
  * `update_mentions.py` → refresh sentiment/risk/summary
  * `run_demo.py` → launches backend + frontend in two separate Terminal windows (local demo)

---

## 📦 Installation

Clone this repository:

```bash
git clone https://github.com/DhaneshRamesh/ai-journalist-monitor.git
cd ai-journalist-monitor
```

Install dependencies globally (Python 3.13+):

```bash
pip install -r requirements.txt
```

*(Or install manually: `pip install fastapi uvicorn sqlalchemy streamlit requests pandas`)*

---

## ▶️ Running Locally

### Option 1: Manual

Start backend:

```bash
uvicorn src.api.app:app --reload
```

Start frontend (in another terminal):

```bash
python3 -m streamlit run frontend/app.py
```

### Option 2: Auto (recommended)

Run both backend + frontend in separate macOS Terminal windows:

```bash
python3 scripts/run_demo.py
```

---

## 🔗 API Endpoints

* **Health** → `GET /api/health`
  Returns `{ "status": "ok" }`

* **Mentions** → `GET /api/mentions?limit=50`
  Returns latest mentions with sentiment, summary, and risk score.

---

## 💻 Frontend Dashboard

* Lists all mentions from API
* Displays title, summary, sentiment, risk score
* Interactive buttons (Flag / Suggest Journalist) — demo placeholders

Run it:

```bash
python3 -m streamlit run frontend/app.py
```

---

## 🗒️ Project Structure

```
ai-journalist-monitor/
├── src/
│   ├── api/               # FastAPI app + endpoints
│   ├── db/                # Database models & sessions
│   └── processing/        # Sentiment, risk, summarizer
├── frontend/              # Streamlit UI
│   └── app.py
├── scripts/               # CLI scripts
│   ├── process_mentions.py
│   ├── update_mentions.py
│   └── run_demo.py
└── README.md
```

---

## ✅ Status

* Backend API working (`/api/health`, `/api/mentions`)
* Processing pipeline creates & updates mentions
* Frontend dashboard running
* Demo script added to launch both services

---

## 📌 Next Steps

* Add **journalist matching** logic
* Enhance **risk scoring** heuristics
* Deploy backend & frontend (Render / Azure Static Apps)

---
