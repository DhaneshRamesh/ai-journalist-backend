# src/processing/risk_detector.py
"""
Risk detector module.

Uses Azure OpenAI to assign a risk score (0–10) based on sensitivity of content.
Falls back to simple keyword matching if Azure config is missing or request fails.
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RISK_KEYWORDS = ["confidential", "proprietary", "leak", "prototype", "internal"]


def _get_azure_config():
    endpoint = os.getenv("ENDPOINT", "").rstrip("/")
    api_ver = os.getenv("API_VER", "2024-06-01")
    key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_DEPLOYMENT_NAME")
    return endpoint, api_ver, key, deployment


def _classify_with_azure(text: str) -> int:
    """
    Ask the model for a numeric risk score (0–10).
    """
    endpoint, api_ver, key, deployment = _get_azure_config()
    if not (endpoint and key and deployment):
        raise RuntimeError("Azure OpenAI config missing.")

    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
    headers = {"api-key": key, "Content-Type": "application/json"}
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a risk classifier. "
                    "Read the text and output a single integer 0–10 (0 = no risk, 10 = highly sensitive). "
                    "Do not explain, only output the number."
                ),
            },
            {"role": "user", "content": text},
        ],
        "max_tokens": 4,
        "temperature": 0.0,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices")
    if not choices:
        raise RuntimeError("No choices in Azure response.")
    msg = choices[0].get("message", {}).get("content", "").strip()
    try:
        score = int(msg)
        return max(0, min(10, score))
    except ValueError:
        logger.warning("Unexpected Azure risk reply: %r", msg)
        return 0


def detect_risk(text: str) -> dict:
    """
    Returns dict: { "risk_score": int, "hits": list }
    - risk_score: 0–10 if Azure works, otherwise keyword count
    - hits: matched keywords (always populated for transparency)
    """
    if not text:
        return {"risk_score": 0, "hits": []}

    hits = [k for k in RISK_KEYWORDS if k in text.lower()]

    try:
        score = _classify_with_azure(text)
        return {"risk_score": score, "hits": hits}
    except Exception as e:
        logger.warning("Azure risk classification failed, falling back: %s", e)
        return {"risk_score": len(hits), "hits": hits}
