from tender_backend.workers.celery_app import app


def test_extract_tasks_route_to_ai_queue() -> None:
    routes = app.conf.task_routes

    assert routes["tender_backend.workers.tasks_extract.*"] == {"queue": "ai_tasks"}
