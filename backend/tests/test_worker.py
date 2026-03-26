from app.core.config import settings
from app.worker import worker_app


def test_worker_uses_configured_broker_and_result_backend() -> None:
    assert worker_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert worker_app.conf.result_backend == settings.CELERY_RESULT_BACKEND
    assert worker_app.conf.task_default_queue == "default"
