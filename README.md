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

## 🗄️ Database Configuration

### Environment Variables

Create a `.env` file in the project root with your database connection string:

```bash
# Example for Azure PostgreSQL
DATABASE_URL=postgresql://myuser@myserver:mypassword@myserver.postgres.database.azure.com:5432/mydb?sslmode=require

# Example for Azure MySQL
# DATABASE_URL=mysql+mysqlconnector://myuser@myserver:mypassword@myserver.mysql.database.azure.com:3306/mydb?ssl_ca=/path/to/ca-cert.pem
```

**Note:** Replace `myuser`, `myserver`, `mypassword`, and `mydb` with your actual Azure database credentials.

---

## ▶️ Running Locally

### Option 1: Manual

Start backend:
```bash
uvicorn src.api.app:app --reload
```

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

## ☁️ Azure Deployment

### Using Azure App Service

When deploying to Azure App Service, configure your environment variables in the Azure portal:

1. Navigate to your App Service in the Azure Portal
2. Go to **Configuration** → **Application settings**
3. Add the `DATABASE_URL` and any other required environment variables
4. Click **Save** and restart your application

**Important:** Azure App Service automatically loads Application settings as environment variables, so you don't need a `.env` file in production.

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
