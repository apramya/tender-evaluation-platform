"""
Celery worker entrypoint.
"""
from celery import Celery

from app.utils.config import settings

celery_app = Celery(
    "tender_evaluation",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
