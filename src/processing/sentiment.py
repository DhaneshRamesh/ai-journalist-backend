import os
import logging
from typing import Tuple
from openai import AzureOpenAI
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)

# Initialize Azure OpenAI client
try:
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2023-05-15"
    )
except Exception as e:
    logger.error(f"Failed to initialize Azure OpenAI client: {e}")
    client = None

# Initialize VADER for fallback
try:
    _analyzer = SentimentIntensityAnalyzer()
except Exception as e:
    logger.error(f"Failed to initialize VADER: {e}")
    _analyzer = None

def _analyze_sentiment(text: str) -> Tuple[str, float]:
    """
    Analyze sentiment using Azure OpenAI GPT-4o-mini.
    Returns (label, score) where score is between -1 (negative) and 1 (positive).
    Fallback to VADER if API fails.
    """
    if not text or not isinstance(text, str):
        logger.warning("Invalid input for sentiment analysis")
        return "neutral", 0.0

    try:
        if client:
            prompt = f"Analyze the sentiment of the following text. Return 'positive', 'negative', or 'neutral' and a score between -1 (very negative) and 1 (very positive) in the format 'label: score':\n\n{text[:2000]}"
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You are an expert sentiment analyzer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.3
            )
            result = response.choices[0].message.content.strip()
            label, score = result.split(":")
            label = label.strip().lower()
            score = float(score.strip())
            if label not in ["positive", "negative", "neutral"]:
                raise ValueError(f"Invalid sentiment label: {label}")
            if not -1.0 <= score <= 1.0:
                raise ValueError(f"Invalid sentiment score: {score}")
            return label, score
        else:
            # Fallback to VADER
            if _analyzer:
                scores = _analyzer.polarity_scores(text or "")
                compound = scores["compound"]
                if compound >= 0.2:
                    return "positive", compound
                elif compound <= -0.2:
                    return "negative", compound
                return "neutral", compound
            # Fallback if VADER fails
            return "neutral", 0.0
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        # Fallback to VADER
        if _analyzer:
            scores = _analyzer.polarity_scores(text or "")
            compound = scores["compound"]
            if compound >= 0.2:
                return "positive", compound
            elif compound <= -0.2:
                return "negative", compound
            return "neutral", compound
        return "neutral", 0.0
