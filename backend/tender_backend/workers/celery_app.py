"""Celery application configuration.

Queues:
  - io_tasks: I/O-bound work (parsing, export, storage)
  - workflow_tasks: Workflow orchestration
"""

from __future__ import annotations

import os

from celery import Celery

broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.environ.get("CELERY_RESULT_BACKEND", broker_url)

app = Celery("tender")

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_routes={
        "tender_backend.workers.tasks_parse.*": {"queue": "io_tasks"},
        "tender_backend.workers.tasks_workflow.*": {"queue": "workflow_tasks"},
    },
    task_default_queue="io_tasks",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

app.autodiscover_tasks(["tender_backend.workers"])
