import ssl
from urllib.parse import urlsplit

from celery import Celery

from app.core.config import settings


def _redis_tls_options(url: str) -> dict[str, ssl.VerifyMode] | None:
    """Require certificate verification for Redis TLS URLs."""

    if urlsplit(url).scheme.lower() == "rediss":
        return {
            "ssl_cert_reqs": ssl.CERT_REQUIRED,
        }

    return None


def create_celery_app(
    broker_url: str,
    result_backend: str,
) -> Celery:
    app = Celery(
        "asklaw",
        broker=broker_url,
        backend=result_backend,
    )

    configuration = {
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
    }

    broker_tls = _redis_tls_options(broker_url)
    if broker_tls is not None:
        configuration["broker_use_ssl"] = broker_tls

    backend_tls = _redis_tls_options(result_backend)
    if backend_tls is not None:
        configuration["redis_backend_use_ssl"] = backend_tls

    app.conf.update(configuration)
    return app


# =========================================================
# CELERY APP
# =========================================================

celery_app = create_celery_app(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
)


# =========================================================
# IMPORT TASKS
# =========================================================

import app.tasks.document_tasks
