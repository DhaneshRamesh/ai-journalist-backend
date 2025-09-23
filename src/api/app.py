from fastapi import FastAPI

app = FastAPI(title='AI Journalist API')

@app.get('/health')
def health():
    return {'status': 'ok'}
