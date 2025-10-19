from src.utils.openai_azure import chat

def summarize_text(text: str) -> str:
    prompt = [
        {"role": "system", "content": "You are a concise news summarizer. Output 2-3 bullet points."},
        {"role": "user", "content": text[:8000]}
    ]
    return chat(prompt)
