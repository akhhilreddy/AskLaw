from celery import Celery


# =========================================================
# CELERY APP
# =========================================================

celery_app = Celery(
    "asklaw",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
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