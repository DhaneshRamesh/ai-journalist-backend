from typing import List, Dict

def rank_journalists(article_text: str, candidates: List[Dict], top_k: int = 5):
    # Dummy scorer; replace with FAISS + LLM re-ranking.
    L = max(len(article_text), 1)
    scored = []
    for c in candidates:
        s = min(len(c.get("topics","")) / L, 1.0)
        scored.append((c, float(s)))
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]
    return [{
        "id": c.get("id", 0),
        "name": c.get("name",""),
        "outlet": c.get("outlet",""),
        "score": round(s*100, 2),
        "reason": "Heuristic ranking (placeholder)"
    } for c, s in ranked]
