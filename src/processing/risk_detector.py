def risk_score(text: str) -> int:
    """
    A super simple heuristic; replace with your own rules or LLM-based classifier.
    """
    t = (text or "").lower()
    score = 0
    for kw in ["fraud","lawsuit","regulator","ban","security breach","scandal","collapse"]:
        if kw in t: score += 20
    return min(score, 100)
