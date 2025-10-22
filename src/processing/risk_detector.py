import os
import logging
from typing import Optional
from openai import AzureOpenAI

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

def risk_score(text: str, sentiment_score: Optional[float] = None) -> float:
    """
    Let GPT-4o-mini dynamically calculate risk score based on text content and business context.
    Returns a score between 0.0 (low risk) and 1.0 (high risk).
    Fallback to keyword-based if API fails.
    """
    if not text or not isinstance(text, str):
        logger.warning("Invalid input for risk score")
        return 0.0

    try:
        if client:
            prompt = f"""
            Analyze the following text for business risks (financial, reputational, operational, legal). 
            Consider the impact on a business and return a single number between 0.0 (low risk) and 1.0 (high risk). 
            Be objective and dynamic based on the content only.

            Text: {text[:2000]}

            Response format: Just the number (e.g., 0.7)
            """
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": "You are an expert risk assessor. Respond with only a number 0.0-1.0."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.1  # Low temperature for consistent scoring
            )
            risk_score = float(response.choices[0].message.content.strip())
            if not 0.0 <= risk_score <= 1.0:
                raise ValueError(f"Invalid risk score: {risk_score}")
            # Dynamically adjust based on sentiment if provided
            if sentiment_score is not None:
                if sentiment_score < -0.1:
                    risk_score = min(1.0, risk_score + 0.2)  # Increase for negative sentiment
                elif sentiment_score > 0.1:
                    risk_score = max(0.0, risk_score - 0.1)  # Decrease for positive sentiment
            return round(risk_score, 2)
        else:
            # Fallback: Original keyword-based heuristic (scaled to 0.0-1.0)
            t = text.lower()
            score = 0
            for kw in ["fraud", "lawsuit", "regulator", "ban", "security breach", "scandal", "collapse"]:
                if kw in t:
                    score += 20
            risk_score = min(score, 100) / 100.0
            if sentiment_score is not None:
                if sentiment_score < -0.1:
                    risk_score = min(1.0, risk_score + 0.2)
                elif sentiment_score > 0.1:
                    risk_score = max(0.0, risk_score - 0.1)
            return round(risk_score, 2)
    except Exception as e:
        logger.error(f"Risk score calculation failed: {e}")
        # Fallback: Original keyword-based heuristic
        t = text.lower()
        score = 0
        for kw in ["fraud", "lawsuit", "regulator", "ban", "security breach", "scandal", "collapse"]:
            if kw in t:
                score += 20
        risk_score = min(score, 100) / 100.0
        if sentiment_score is not None:
            if sentiment_score < -0.1:
                risk_score = min(1.0, risk_score + 0.2)
            elif sentiment_score > 0.1:
                risk_score = max(0.0, risk_score - 0.1)
        return round(risk_score, 2)
