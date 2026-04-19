from celery import Celery

celery = Celery(
    "classifier",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)