from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import threading

from src.db.models import get_session, Mention
# Scripts: expose these so API can run them
from scripts.ingest_once import main as ingest_once_main
from scripts.process_mentions import process_all as process_mentions_main
from src.processing.summarizer import summarize_text

# Azure OpenAI test endpoint
import openai

router = APIRouter()

class MentionOut(BaseModel):
    id: int
    article_id: int
    title: Optional[str]
    summary: Optional[str]
    sentiment: Optional[str]
    risk_score: Optional[int]
    source: Optional[str]
    url: Optional[str]

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/mentions", response_model=List[MentionOut])
def get_mentions(limit: int = 50):
    session = get_session()
    q = session.query(Mention).order_by(Mention.created_at.desc()).limit(limit).all()
    results = []
    for m in q:
        a = m.article
        results.append({
            "id": m.id,
            "article_id": m.article_id,
            "title": a.title if a else None,
            "summary": m.summary,
            "sentiment": m.sentiment,
            "risk_score": m.risk_score,
            "source": a.source if a else None,
            "url": a.link if a else None
        })
    session.close()
    return results

# --- Azure OpenAI test ---
@router.get("/ai-test")
def ai_test():
    endpoint = os.getenv("ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_DEPLOYMENT_NAME")
    api_ver = os.getenv("API_VER", "2024-06-01")

    if not (endpoint and api_key and deployment):
        raise HTTPException(
            status_code=400,
            detail="Azure OpenAI configuration missing (ENDPOINT/AZURE_OPENAI_KEY/AZURE_DEPLOYMENT_NAME)."
        )

    client = openai.AzureOpenAI(
        api_key=api_key,
        api_version=api_ver,
        azure_endpoint=endpoint,
    )
    resp = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": "Say hello in one word"}],
        max_tokens=8,
    )
    return {"status_code": 200, "body": resp.model_dump()}

# --- Admin-protected operations ---

def _check_admin_token(request: Request):
    token = request.headers.get("X-ADMIN-TOKEN") or request.query_params.get("admin_token")
    expected = os.getenv("ADMIN_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=403, detail="ADMIN_API_TOKEN not configured on server.")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid admin token.")

def _run_in_background(fn, *args, **kwargs):
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return {"status": "started_in_background"}

@router.post("/ingest")
def run_ingest(request: Request):
    """Trigger ingestion of new articles."""
    _check_admin_token(request)
    return _run_in_background(ingest_once_main)

@router.post("/process")
def run_process(request: Request):
    """Trigger processing pipeline (summarize/sentiment/risk)."""
    _check_admin_token(request)
    return _run_in_background(process_mentions_main)
