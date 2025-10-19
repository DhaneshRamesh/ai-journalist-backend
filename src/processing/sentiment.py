from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
_analyzer = SentimentIntensityAnalyzer()

def classify(text: str) -> str:
    s = _analyzer.polarity_scores(text or "")
    if s["compound"] >= 0.2: return "positive"
    if s["compound"] <= -0.2: return "negative"
    return "neutral"
