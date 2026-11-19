"""Celery worker entry point. Later phases register notification delivery, payroll and report tasks here."""
from celery import Celery

from app.core.config import get_settings

_s = get_settings()
celery_app = Celery("talvynza", broker=_s.redis_url or "memory://", backend=_s.redis_url or "cache+memory://")
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], task_acks_late=True, task_default_queue="talvynza"
)


@celery_app.task(name="talvynza.ping")
def ping() -> str:
    return "pong"
