"""
src/matcher/match_journalists.py

Functions:
- retrieve_candidates(article_text, top_k=10) -> list of candidates from FAISS
- gpt_rank(article_text, candidates) -> uses OpenAI chat to score & explain candidates
- match(article_text, top_k=5) -> combined pipeline returning ranked matches
- generate_pitch(article_summary, journalist) -> optional personalized pitch JSON

Usage:
  export OPENAI_API_KEY="sk-..."
  from src.matcher.match_journalists import match
  matches = match("Short article summary or full text", top_k=5)
"""

import os
import json
import re
from pathlib import Path
import numpy as np

try:
    import faiss
except Exception:
    raise RuntimeError("faiss not installed. pip install faiss-cpu")

try:
    from openai import OpenAI
except Exception:
    raise RuntimeError("OpenAI SDK not found. Install with: pip install openai")

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = REPO_ROOT / "data" / "journalists.faiss"
META_PATH = REPO_ROOT / "data" / "journalists_meta.json"

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"  # change to model you have access to

def _get_client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=key)

def embed_text(text: str):
    client = _get_client()
    prompt = text if len(text) < 15000 else text[:15000]
    resp = client.embeddings.create(model=EMBED_MODEL, input=prompt)
    emb = np.array(resp.data[0].embedding, dtype=np.float32)
    return emb

def load_index_and_meta():
    if not INDEX_PATH.exists() or not META_PATH.exists():
        raise RuntimeError(f"Index or meta missing. Run scripts/build_journalist_index.py first. Expected: {INDEX_PATH}, {META_PATH}")
    idx = faiss.read_index(str(INDEX_PATH))
    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return idx, meta

def retrieve_candidates(article_text: str, top_k: int = 10):
    """
    Returns list of {"score": distance, "meta": meta_dict}
    Note: FAISS IndexFlatL2 returns L2 distances (lower = closer)
    """
    idx, meta = load_index_and_meta()
    qv = embed_text(article_text).reshape(1, -1)
    D, I = idx.search(qv, top_k)
    results = []
    for dist, i in zip(D[0], I[0]):
        m = meta[int(i)]
        results.append({"dist": float(dist), "meta": m})
    return results

def _extract_json_from_text(text: str):
    """Try to find JSON array/object in text and parse it."""
    # First try to find the first { ... } or [ ... ] block
    m = re.search(r"(\[{1}[\s\S]*\]{1})", text)
    if not m:
        # fallback to object
        m = re.search(r"(\{[\s\S]*\})", text)
        if not m:
            return None
    try:
        return json.loads(m.group(1))
    except Exception:
        # attempt to fix common trailing commas issues
        cleaned = re.sub(r",\s*}", "}", m.group(1))
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            return None

def gpt_rank(article_text: str, candidates: list):
    """
    Uses OpenAI chat to ask for a 0-100 score and one-line reason for each candidate.
    Expects `candidates` to be a list of dicts with 'meta' keys (meta is the CSV row)
    Returns parsed JSON (list of objects with id, name, outlet, score, reason)
    """
    client = _get_client()

    cand_summary = []
    for c in candidates:
        m = c["meta"]
        cand_summary.append({
            "id": m.get("id"),
            "name": m.get("name"),
            "outlet": m.get("outlet"),
            "beats": m.get("beats"),
            "recent_articles": m.get("recent_articles")
        })
    system = "You are an expert news editor who understands journalist beats and interests."
    user_prompt = f"""
Article summary:
\"\"\"{article_text}\"\"\"

Below are candidate journalists (id, name, outlet, beats, recent_articles).
For each candidate, return a JSON array where each element has:
- id (journalist id),
- name,
- outlet,
- score (integer 0-100, how likely they are to be interested in covering this article),
- reason (one concise sentence explaining the match).

Candidates:
{json.dumps(cand_summary, indent=2)}
"""

    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=700,
        temperature=0.2
    )

    content = resp.choices[0].message["content"]
    parsed = _extract_json_from_text(content)
    if parsed is None:
        # If GPT didn't return clean JSON, return a fallback simple mapping with equal scores
        fallback = []
        for c in candidates:
            m = c["meta"]
            fallback.append({
                "id": m.get("id"),
                "name": m.get("name"),
                "outlet": m.get("outlet"),
                "score": 50,
                "reason": "Fallback: unable to parse model output."
            })
        return fallback
    return parsed

def match(article_text: str, top_k: int = 5):
    """
    Full pipeline: retrieve top candidates from index, then ask GPT to rank them,
    and return sorted top_k matches.
    """
    candidates = retrieve_candidates(article_text, top_k=10)
    ranked = gpt_rank(article_text, candidates)
    # make sure numeric score exists
    for r in ranked:
        try:
            r["score"] = int(r.get("score", 0))
        except Exception:
            try:
                r["score"] = int(float(r.get("score", 0)))
            except Exception:
                r["score"] = 0
    ranked_sorted = sorted(ranked, key=lambda x: x["score"], reverse=True)[:top_k]
    return ranked_sorted

def generate_pitch(article_summary: str, journalist: dict):
    """
    Produce a JSON object with subject and body fields tailored to the journalist.
    journalist: dict with keys name, outlet, beats (optional)
    """
    client = _get_client()
    prompt = f"""
Write a concise email pitch for journalist {journalist.get('name')} at {journalist.get('outlet')}.
Use a subject line (<=60 chars) and a short body (2-3 sentences).
Mention why this article (summary below) matters to their audience and reference their beats.

Article summary:
\"\"\"{article_summary}\"\"\"
Return JSON: {{ "subject": "...", "body": "..." }}
"""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role":"user","content":prompt}],
        max_tokens=250,
        temperature=0.2,
    )
    out = resp.choices[0].message["content"]
    j = _extract_json_from_text(out)
    if j is None:
        # fallback simple wrapper
        return {"subject": f"Story idea: {article_summary[:50]}...", "body": article_summary}
    return j

if __name__ == "__main__":
    # quick local test example
    sample = "A concise summary describing an AI startup that just open-sourced a novel model for edge devices."
    print("Retrieving matches for sample text...")
    try:
        matches = match(sample, top_k=5)
        print(json.dumps(matches, indent=2))
    except Exception as e:
        print("Error running match():", e)
        print("Ensure you have built the index and set OPENAI_API_KEY.")