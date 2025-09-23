from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from src.api.endpoints import router as endpoints_router

app = FastAPI(title="AI Journalist API")
app.include_router(endpoints_router, prefix="/api")

@app.get("/")
def root():
    return RedirectResponse(url="/api/health")
