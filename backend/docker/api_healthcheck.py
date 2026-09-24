"""Dependency-aware health check for the production API container."""

from urllib.request import urlopen

from pymongo import MongoClient
from redis import Redis

from app.core.config import settings


def require_http(url: str) -> None:
    with urlopen(url, timeout=5) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Unhealthy HTTP dependency: {url}")


require_http("http://127.0.0.1:8000/health")

mongo = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5_000)
try:
    mongo.admin.command("ping")
finally:
    mongo.close()

Redis.from_url(
    settings.CELERY_BROKER_URL,
    socket_connect_timeout=5,
    socket_timeout=5,
).ping()

require_http(f"{settings.QDRANT_URL.rstrip('/')}/readyz")
require_http(settings.SEARXNG_URL.removesuffix("/search") + "/healthz")
