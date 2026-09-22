from celery import Celery

from app.core.config import settings


# =========================================================
# CELERY APP
# =========================================================

celery_app = Celery(
    "asklaw",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)


# =========================================================
# TASK SETTINGS
# =========================================================

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


# =========================================================
# IMPORT TASKS
# =========================================================

import app.tasks.document_tasks
