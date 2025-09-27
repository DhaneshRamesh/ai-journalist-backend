#!/usr/bin/env python3
"""
Build a journalist embeddings FAISS index.
Supports:
 - Azure OpenAI (uses Azure REST embeddings endpoint)
 - OpenAI public API (uses openai Python package)

Expected environment variables (choose one provider):
  # Azure
  AZURE_OPENAI_KEY
  AZURE_OPENAI_ENDPOINT            (e.g. https://my-resource.openai.azure.com)
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT (e.g. text-embedding-3-small)
  AZURE_OPENAI_API_VERSION         (optional, default 2024-06-01)

  # Public OpenAI
  OPENAI_API_KEY
  OPENAI_EMBEDDING_MODEL           (e.g. text-embedding-3-small)

Other:
  JOURNALISTS_SOURCE               (path to JSON/CSV; default data/journalists.json)
  OUTPUT_FAISS_PATH                (default data/journalists.faiss)
  OUTPUT_META_PATH                 (default data/journalists_meta.json)
"""

import os
import json
import sys
import time
import logging
from typing import List, Dict

# third-party libs
try:
    import requests
except Exception:
    print("Please `pip install requests`")
    raise

try:
    import faiss
except Exception:
    print("Please `pip install faiss-cpu` (or faiss) to use FAISS")
    raise

# optional convenience for OpenAI public API
USE_OPENAI_PY_PACKAGE = False
if os.getenv("OPENAI_API_KEY"):
    try:
        import openai
        USE_OPENAI_PY_PACKAGE = True
    except Exception:
        # we'll fallback to direct REST for OpenAI if package not installed
        USE_OPENAI_PY_PACKAGE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# --------- Config and helpers ----------
AZURE_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

JOURNALISTS_SOURCE = os.getenv("JOURNALISTS_SOURCE", "data/journalists.json")
OUTPUT_FAISS_PATH = os.getenv("OUTPUT_FAISS_PATH", "data/journalists.faiss")
OUTPUT_META_PATH = os.getenv("OUTPUT_META_PATH", "data/journalists_meta.json")

# simple loader that accepts JSON list or CSV with 'id' and 'text' columns
def load_journalists(path: str) -> List[Dict]:
    if not os.path.exists(path):
        logging.error(f"Source file not found: {path}")
        sys.exit(1)
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                # maybe { "journalists": [...] }
                if "journalists" in data and isinstance(data["journalists"], list):
                    return data["journalists"]
                # or single object -> wrap
                return [data]
            return data
    elif path.lower().endswith(".csv"):
        import csv
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
        return rows
    else:
        logging.error("Unsupported source format (expect .json or .csv)")
        sys.exit(1)

# -------- Embedding callers ----------
def embed_with_azure(texts: List[str]) -> List[List[float]]:
    """
    Azure embeddings REST call:
    POST {AZURE_ENDPOINT}/openai/deployments/{deployment}/embeddings?api-version={api_version}
    Header: api-key
    """
    assert AZURE_KEY and AZURE_ENDPOINT and AZURE_DEPLOYMENT, "Azure env vars not set"
    url = AZURE_ENDPOINT.rstrip("/") + f"/openai/deployments/{AZURE_DEPLOYMENT}/embeddings?api-version={AZURE_API_VERSION}"
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_KEY,
    }
    payload = {"input": texts}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Azure embeddings request failed: {resp.status_code} - {resp.text}")
    body = resp.json()
    # Azure returns { data: [{embedding: [...]} , ...], ... }
    embeddings = [d["embedding"] for d in body.get("data", [])]
    return embeddings

def embed_with_openai_public(texts: List[str]) -> List[List[float]]:
    """
    Public OpenAI: try python package first, otherwise REST.
    """
    if USE_OPENAI_PY_PACKAGE:
        openai.api_key = OPENAI_KEY
        # older openai python package uses openai.Embedding.create
        try:
            result = openai.Embedding.create(model=OPENAI_MODEL, input=texts)
            embeddings = [item["embedding"] for item in result["data"]]
            return embeddings
        except Exception as e:
            logging.warning("openai package call failed; falling back to REST. Error: %s", e)

    # REST fallback for public OpenAI
    url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {"model": OPENAI_MODEL, "input": texts}
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI embeddings request failed: {resp.status_code} - {resp.text}")
    body = resp.json()
    embeddings = [d["embedding"] for d in body.get("data", [])]
    return embeddings

# -------- Main ----------
def main():
    logging.info("Loading journalists from %s", JOURNALISTS_SOURCE)
    rows = load_journalists(JOURNALISTS_SOURCE)
    logging.info("Loaded %d rows", len(rows))

    # prepare texts and metadata
    texts = []
    metadata = []
    for idx, r in enumerate(rows):
        # support variations: use r['text'] or r['bio'] or combine name+bio
        text = None
        if isinstance(r, str):
            text = r
            meta = {"id": idx}
        elif isinstance(r, dict):
            text = r.get("text") or r.get("bio") or " ".join(str(r.get(k, "")) for k in ("name","title")) or ""
            meta = {"id": r.get("id", idx), "name": r.get("name"), "source": r.get("source")}
        else:
            text = str(r)
            meta = {"id": idx}
        texts.append(text)
        metadata.append(meta)

    # call embeddings in batches to be safe with payload sizes
    embeddings = []
    batch_size = 16
    failed_rows = []
    logging.info("Detected provider: %s", "Azure" if AZURE_KEY else "OpenAI public")
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i+batch_size]
        try:
            if AZURE_KEY:
                emb = embed_with_azure(batch_texts)
            else:
                if not OPENAI_KEY:
                    raise RuntimeError("No OPENAI_API_KEY or AZURE_OPENAI_KEY set")
                emb = embed_with_openai_public(batch_texts)
            if len(emb) != len(batch_texts):
                logging.warning("Embedding count mismatch for batch starting at %d", i)
            embeddings.extend(emb)
            logging.info("Embedded batch %d - %d", i, i+len(batch_texts)-1)
            time.sleep(0.1)  # avoid spiky rate limits
        except Exception as e:
            logging.error("Embedding failed for batch starting at %d: %s", i, e)
            # mark individual rows as failed
            for j in range(i, i+len(batch_texts)):
                failed_rows.append({"index": j, "error": str(e)})
            # continue to next batch

    logging.info("Total embeddings produced: %d (failed rows: %d)", len(embeddings), len(failed_rows))

    # If some rows failed, pad with zero vectors so index dims match
    dim = None
    if embeddings:
        dim = len(embeddings[0])
    else:
        # fallback default (embedding dims commonly 1536)
        dim = 1536
        logging.warning("No embeddings produced; using fallback dim=%d", dim)

    # ensure embeddings list length == number of rows by adding zeros for failed rows
    full_embeddings = []
    emb_iter = iter(embeddings)
    for idx in range(len(texts)):
        if any(f.get("index") == idx for f in failed_rows):
            full_embeddings.append([0.0]*dim)
        else:
            # safe-get from produced embeddings
            try:
                e = next(emb_iter)
                if len(e) != dim:
                    # resize if strange
                    logging.warning("Embedding dimension mismatch at idx %d", idx)
                    e = e + [0.0]*(dim - len(e)) if len(e) < dim else e[:dim]
                full_embeddings.append(e)
            except StopIteration:
                full_embeddings.append([0.0]*dim)

    import numpy as np
    X = np.array(full_embeddings, dtype="float32")
    logging.info("Embedding matrix shape: %s", X.shape)

    # build faiss index (IndexFlatL2)
    index = faiss.IndexFlatL2(dim)
    index.add(X)
    logging.info("FAISS index size: %d", index.ntotal)

    # write index and metadata
    os.makedirs(os.path.dirname(OUTPUT_FAISS_PATH) or ".", exist_ok=True)
    faiss.write_index(index, OUTPUT_FAISS_PATH)
    with open(OUTPUT_META_PATH, "w", encoding="utf-8") as f:
        out_meta = {"metadata": metadata, "failed_rows": failed_rows}
        json.dump(out_meta, f, ensure_ascii=False, indent=2)
    logging.info("Wrote FAISS index to %s", OUTPUT_FAISS_PATH)
    logging.info("Wrote metadata to %s", OUTPUT_META_PATH)
    logging.info("Done.")

if __name__ == "__main__":
    main()