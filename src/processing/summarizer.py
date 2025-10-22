import os
import logging
from typing import Optional
from src.utils.openai_azure import chat

logger = logging.getLogger(__name__)

def summarize_text(text: str, max_length: int = 100, min_length: int = 30) -> Optional[str]:
    """
    Generate a concise summary in 2-3 bullet points using Azure OpenAI GPT-4o-mini.
    Fallback to truncation if API fails.
    """
    if not text or not isinstance(text, str):
        logger.warning("Invalid input text for summarization")
        return ""

    try:
        prompt = [
            {"role": "system", "content": f"You are a concise news summarizer. Output 2-3 bullet points, total {min_length} to {max_length} words."},
            {"role": "user", "content": text[:8000]}
        ]
        summary = chat(prompt, model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"))
        if not summary:
            raise ValueError("Empty summary returned")
        word_count = len(summary.split())
        if min_length <= word_count <= max_length:
            return summary
        return summary[:max_length] + "..." if word_count > max_length else summary
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        # Fallback: Extract first few sentences
        sentences = text.split('. ')
        summary = '. '.join(sentences[:2])[:max_length]
        return summary + ("..." if len(summary) >= max_length else "")
