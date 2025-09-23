# src/processing/sentiment.py
# Uses vaderSentiment package (no NLTK data download required)

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

sia = SentimentIntensityAnalyzer()

def map_sentiment_from_text(text: str):
    """
    Returns (label, compound_score).
    label in {"Positive","Neutral","Negative"} based on compound thresholds.
    """
    if not text:
        return "Neutral", 0.0
    scores = sia.polarity_scores(text)
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