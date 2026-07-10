from fastapi import FastAPI

from app.core.config import settings
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
)
@app.get("/")
def root():
    return {"message": "Welcome to AskLaw API"}

@app.get("/health")
def health():
    return {"status": "healthy"}