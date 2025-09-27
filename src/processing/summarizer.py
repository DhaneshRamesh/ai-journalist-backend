# src/processing/summarizer.py
"""
Summarizer module using Azure OpenAI chat completions.
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def summarize_text(text: str) -> str:
    """
    Summarize text using Azure OpenAI deployment.
    Falls back to truncation if API call fails.
    """
    if not text:
        return ""

    endpoint = os.getenv("ENDPOINT", "").rstrip("/")
    api_ver = os.getenv("API_VER", "2024-06-01")
    key = os.getenv("AZURE_OPENAI_KEY")
    deployment = os.getenv("AZURE_DEPLOYMENT_NAME")

    if not (endpoint and api_ver and key and deployment):
        logger.warning("Missing Azure OpenAI config, falling back to naive summarization.")
        return text[:200] + ("..." if len(text) > 200 else "")

    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_ver}"
    headers = {"api-key": key, "Content-Type": "application/json"}
    payload = {
        "messages": [
            {"role": "system", "content": "You are a concise summarizer. Return 1-2 sentences only."},
            {"role": "user", "content": f"Summarize:\n\n{text}"}
        ],
        "max_tokens": 120,
        "temperature": 0.0
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # extract reply safely
        choices = data.get("choices")
        if choices and "message" in choices[0]:
            return choices[0]["message"]["content"].strip()
        elif choices and "text" in choices[0]:
            return choices[0]["text"].strip()
        return text[:200] + ("..." if len(text) > 200 else "")
    except Exception as e:
        logger.error("Summarization failed: %s", e)
        return text[:200] + ("..." if len(text) > 200 else "")