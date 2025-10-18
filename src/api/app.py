from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv()
from fastapi.responses import RedirectResponse
from src.api.endpoints import router as endpoints_router

app = FastAPI(title="AI Journalist API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai-journalist-frontend-ddf2ejc2f5h0hzf0.canadacentral-01.azurewebsites.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(endpoints_router, prefix="/api")

@app.get("/")
def root():
    return RedirectResponse(url="/api/health")
