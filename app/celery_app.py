import os
from celery import Celery


celery = Celery(
    "classifier",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
)


celery.conf.update(
    imports=["tasks"],
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
)
