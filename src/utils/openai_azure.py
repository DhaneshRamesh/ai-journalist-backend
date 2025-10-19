import os, requests

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
KEY = os.getenv("AZURE_OPENAI_KEY")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
CHAT_DEPLOY = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")
EMBED_DEPLOY = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")

def chat(messages, temperature=0.2):
    if not ENDPOINT or not KEY:
        return "Azure OpenAI not configured."
    url = f"{ENDPOINT}/openai/deployments/{CHAT_DEPLOY}/chat/completions?api-version={API_VERSION}"
    headers = {"api-key": KEY, "Content-Type": "application/json"}
    body = {"messages": messages, "temperature": temperature}
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

def embed(texts):
    if not ENDPOINT or not KEY:
        return []
    url = f"{ENDPOINT}/openai/deployments/{EMBED_DEPLOY}/embeddings?api-version={API_VERSION}"
    headers = {"api-key": KEY, "Content-Type": "application/json"}
    body = {"input": texts}
    r = requests.post(url, headers=headers, json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    return [d["embedding"] for d in data["data"]]
