# src/processing/sentiment.py
"""
Sentiment analysis module.

Uses Azure OpenAI for classification (Positive / Neutral / Negative).
Falls back to VADER sentiment if Azure config is missing or fails.
"""

import os
import requests
import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# fallback VADER analyzer
_vader = SentimentIntensityAnalyzer()


def _get_azure_config():
    endpoint = os.getenv("ENDPOINT", "").rstrip("/")
    api_ver = os.getenv("API_VER", "2024-06-01")
    key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_DEPLOYMENT_NAME")
    return endpoint, api_ver, key, deployment


def _classify_with_azure(text: str) -> str:
    endpoint, api_ver, key, deployment = _get_azure_config()
    if not (endpoint and key and deployment):
        raise RuntimeError("Azure OpenAI config missing.")

    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
    headers = {"api-key": key, "Content-Type": "application/json"}
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "You are a sentiment classifier. Respond with exactly one word: Positive, Negative, or Neutral.",
            },
            {"role": "user", "content": text},
        ],
        "max_tokens": 2,
        "temperature": 0.0,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices")
    if not choices:
        raise RuntimeError("No choices in Azure response.")
    msg = choices[0].get("message", {}).get("content", "").strip()
    if msg not in {"Positive", "Negative", "Neutral"}:
        logger.warning("Unexpected Azure sentiment reply: %r", msg)
        return "Neutral"
    return msg


def map_sentiment_from_text(text: str):
    """
    Returns (label, score).
    - label in {"Positive","Neutral","Negative"}.
    - score is VADER compound (for fallback/debugging).
    """
    if not text:
        return "Neutral", 0.0

    try:
        label = _classify_with_azure(text)
        return label, 0.0
    except Exception as e:
        logger.warning("Azure sentiment failed, falling back to VADER: %s", e)
        scores = _vader.polarity_scores(text)
        compound = scores.get("compound", 0.0)
        if compound <= -0.2:
            label = "Negative"
        elif compound >= 0.2:
            label = "Positive"
        else:
            label = "Neutral"
        return label, compound


def map_sentiment(score: float) -> str:
    if score < -0.2:
        return "Negative"
    if score > 0.2:
        return "Positive"
    return "Neutral"
