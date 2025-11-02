import os
import requests
import logging

logger = logging.getLogger(__name__)

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
KEY = os.getenv("AZURE_OPENAI_KEY")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
CHAT_DEPLOY = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
EMBED_DEPLOY = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")

def chat(messages, model: str = None, temperature: float = 0.2):
    """
    Chat completion using Azure OpenAI REST API.
    Accepts optional `model` for compatibility with summarizer.py.
    """
    if not ENDPOINT or not KEY:
        logger.warning("Azure OpenAI not configured.")
        return "Azure OpenAI not configured."

    deploy = model or CHAT_DEPLOY
    url = f"{ENDPOINT}/openai/deployments/{deploy}/chat/completions?api-version={API_VERSION}"
    headers = {"api-key": KEY, "Content-Type": "application/json"}

    body = {
        "model": deploy,                # ✅ required by REST API
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 300,
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Azure chat API failed: {e}")
        return ""

def embed(texts):
    """Return embeddings via Azure OpenAI REST API."""
    if not ENDPOINT or not KEY:
        logger.warning("Azure OpenAI not configured.")
        return []

    url = f"{ENDPOINT}/openai/deployments/{EMBED_DEPLOY}/embeddings?api-version={API_VERSION}"
    headers = {"api-key": KEY, "Content-Type": "application/json"}

    body = {
        "model": EMBED_DEPLOY,          # ✅ required by REST API
        "input": texts,
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        return [d["embedding"] for d in data["data"]]
    except Exception as e:
        logger.error(f"Azure embedding API failed: {e}")
        return []
