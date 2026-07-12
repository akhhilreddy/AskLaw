from fastapi import FastAPI


from app.api.router import api_router
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
)
app.include_router(api_router)