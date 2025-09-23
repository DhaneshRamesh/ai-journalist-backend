RISK_KEYWORDS = ["confidential", "proprietary", "leak", "prototype", "internal"]

def detect_risk(text: str) -> dict:
    if not text:
        return {"risk_score": 0, "hits": []}
    hits = [k for k in RISK_KEYWORDS if k in text.lower()]
    return {"risk_score": len(hits), "hits": hits}
