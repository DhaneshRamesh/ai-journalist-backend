# src/processing/summarizer.py
from bs4 import BeautifulSoup

def summarize_text(text: str) -> str:
    """
    Minimal summarizer: strip HTML and return first 200 chars + ellipsis.
    Replace later with LLM summarisation for higher quality.
    """
    if not text:
        return ""
    # strip HTML
    clean = BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)
    out = clean.strip()
    return out[:200] + ("..." if len(out) > 200 else "")
