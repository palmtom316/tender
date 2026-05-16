from uuid import uuid4

from tender_backend.workflows.states import WorkflowState


def test_enqueue_technical_generation_creates_pending_run(monkeypatch) -> None:
    captured = {}

    class _Repo:
        async def create_run(self, **kwargs):
            captured["create_run"] = kwargs

        async def save_context(self, run_id, data):
            captured["save_context"] = {"run_id": run_id, "data": data}

    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async._build_repo",
        lambda conn=None: _Repo(),
        raising=False,
    )
    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async.start_background_generation",
        lambda **kwargs: captured.setdefault("background", kwargs),
        raising=False,
    )

    from tender_backend.services.technical_generation_async import enqueue_technical_generation

    result = enqueue_technical_generation(
        project_id=str(uuid4()),
        chapter_id=str(uuid4()),
        created_by="Developer",
        rewrite_note=None,
        target_pages=100,
    )

    assert result["state"] == "pending"
    assert captured["create_run"]["workflow_name"] == "generate_section_async"
    assert captured["background"]["run_id"] == result["run_id"]


def test_get_technical_generation_run_status_maps_completed_context(monkeypatch) -> None:
    run_id = "run-123"
    project_id = str(uuid4())
    chapter_id = str(uuid4())

    class _Repo:
        async def get_run(self, _run_id):
            return {
                "id": run_id,
                "project_id": project_id,
                "state": "completed",
                "current_step": "save_draft",
                "error_message": None,
                "context_json": {"chapter_id": chapter_id, "draft_id": "draft-456"},
            }

    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async._build_repo",
        lambda conn=None: _Repo(),
        raising=False,
    )

    from tender_backend.services.technical_generation_async import get_technical_generation_run_status

    result = get_technical_generation_run_status(project_id=project_id, run_id=run_id)

    assert result["state"] == "completed"
    assert result["draft_id"] == "draft-456"
    assert result["chapter_id"] == chapter_id


def test_get_technical_generation_run_status_includes_progress(monkeypatch) -> None:
    run_id = "run-789"
    project_id = str(uuid4())

    class _Repo:
        async def get_run(self, _run_id):
            return {
                "id": run_id,
                "project_id": project_id,
                "state": "running",
                "current_step": "generate_chapter",
                "error_message": None,
                "context_json": {
                    "chapter_id": str(uuid4()),
                    "draft_id": "draft-999",
                    "completed_sections": 3,
                    "total_sections": 15,
                    "percent": 20,
                    "last_section_code": "8.3",
                },
            }

    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async._build_repo",
        lambda conn=None: _Repo(),
        raising=False,
    )

    from tender_backend.services.technical_generation_async import get_technical_generation_run_status

    result = get_technical_generation_run_status(project_id=project_id, run_id=run_id)

    assert result["state"] == "running"
    assert result["progress"]["completed_sections"] == 3
    assert result["progress"]["total_sections"] == 15
    assert result["progress"]["percent"] == 20
    assert result["progress"]["last_section_code"] == "8.3"


def test_get_technical_generation_run_status_includes_round_progress(monkeypatch) -> None:
    run_id = "run-790"
    project_id = str(uuid4())

    class _Repo:
        async def get_run(self, _run_id):
            return {
                "id": run_id,
                "project_id": project_id,
                "state": "running",
                "current_step": "generate_chapter",
                "error_message": None,
                "context_json": {
                    "chapter_id": str(uuid4()),
                    "current_round": 2,
                    "max_rounds": 4,
                    "last_event": "round_progress",
                },
            }

    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async._build_repo",
        lambda conn=None: _Repo(),
        raising=False,
    )

    from tender_backend.services.technical_generation_async import get_technical_generation_run_status

    result = get_technical_generation_run_status(project_id=project_id, run_id=run_id)

    assert result["progress"]["current_round"] == 2
    assert result["progress"]["max_rounds"] == 4
    assert result["progress"]["last_event"] == "round_progress"


def test_async_runner_marks_failed_on_generation_error(monkeypatch) -> None:
    run_id = "run-failed"
    project_id = str(uuid4())
    chapter_id = str(uuid4())
    captured = {"state": "pending", "error_message": None}

    class _Conn:
        aborted = False

        def commit(self):
            if self.aborted:
                raise RuntimeError("current transaction is aborted")
            captured["commits"] = captured.get("commits", 0) + 1

        def rollback(self):
            self.aborted = False
            captured["rollbacks"] = captured.get("rollbacks", 0) + 1

    class _ConnectionContext:
        def __enter__(self):
            self.conn = _Conn()
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Pool:
        def connection(self):
            return _ConnectionContext()

    class _Repo:
        def __init__(self, conn):
            self._conn = conn

        async def get_run(self, _run_id):
            return {
                "id": run_id,
                "project_id": project_id,
                "state": captured["state"],
                "current_step": captured.get("current_step"),
                "error_message": captured["error_message"],
                "context_json": {"chapter_id": chapter_id},
            }

        async def update_run_state(self, _run_id, state, *, error=None):
            if self._conn.aborted:
                raise RuntimeError("current transaction is aborted")
            captured["state"] = state
            if error is not None:
                captured["error_message"] = error

        async def update_run_current_step(self, _run_id, step_name):
            if self._conn.aborted:
                raise RuntimeError("current transaction is aborted")
            captured["current_step"] = step_name

    def _raise_timeout(self, *args, **kwargs):
        args[0].aborted = True
        raise TimeoutError("timeout while generating")

    monkeypatch.setattr("tender_backend.services.technical_generation_async.get_pool", lambda **kwargs: _Pool())
    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async._build_repo",
        lambda conn=None: _Repo(conn),
        raising=False,
    )
    monkeypatch.setattr(
        "tender_backend.services.technical_generation_async.TechnicalBidWriter.generate_chapter",
        _raise_timeout,
    )

    from tender_backend.services.technical_generation_async import (
        _run_background_generation,
        get_technical_generation_run_status,
    )

    _run_background_generation(run_id=run_id, project_id=project_id)
    result = get_technical_generation_run_status(project_id=project_id, run_id=run_id)

    assert result["state"] == WorkflowState.FAILED
    assert "timeout" in result["error"]
    assert captured["rollbacks"] == 1
