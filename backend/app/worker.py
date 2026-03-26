from celery import Celery

from app.core.config import settings

worker_app = Celery(
    "pivot_backend_build_team",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

worker_app.conf.task_default_queue = "default"
