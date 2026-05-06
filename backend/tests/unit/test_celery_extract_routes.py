from tender_backend.workers.celery_app import app
from tender_backend.workers import tasks_extract
from tender_backend.services.extract_service.ai_requirements_extractor import AiExtractionRunSummary, BatchUsage
from tender_backend.services.extract_service.retry_policy import (
    backoff_countdown_seconds,
    degraded_reasoning_effort,
    pro_review_batch_index,
    provider_limit_for,
    retry_batch_index,
    should_create_retry_batches,
    split_chunk_ids_for_retry,
)


def test_extract_tasks_route_to_ai_queue() -> None:
    routes = app.conf.task_routes

    assert routes["tender_backend.workers.tasks_extract.*"] == {"queue": "ai_tasks"}


def test_high_value_uncertain_missing_zero_output_needs_review() -> None:
    usage = BatchUsage(
        source_file="招标文件.docx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"has_requirements": False, "suspected_missing": True, "empty_reason": "uncertain_missing"},
    )

    assert tasks_extract._needs_review_for_empty_output(
        batch={"metadata_json": {"high_value": True}},
        chunks=[{"text": "投标人资格要求：须具备有效资质。"}],
        usage=usage,
    )


def test_low_value_zero_output_without_suspected_missing_does_not_need_review() -> None:
    usage = BatchUsage(
        source_file="普通附件.docx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"has_requirements": False, "suspected_missing": False, "empty_reason": "true_empty"},
    )

    assert not tasks_extract._needs_review_for_empty_output(
        batch={"metadata_json": {"high_value": False}},
        chunks=[{"text": "普通说明文字。"}],
        usage=usage,
    )


def test_suspected_missing_zero_output_needs_review() -> None:
    usage = BatchUsage(
        source_file="附件.docx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"has_requirements": False, "suspected_missing": True, "empty_reason": "uncertain_missing"},
    )

    assert tasks_extract._needs_review_for_empty_output(
        batch={"metadata_json": {"high_value": False}},
        chunks=[{"text": "普通说明文字。"}],
        usage=usage,
    )


def test_high_value_template_blank_zero_output_does_not_need_review() -> None:
    usage = BatchUsage(
        source_file="合同模板.docx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"has_requirements": False, "suspected_missing": False, "empty_reason": "template_blank"},
    )

    assert not tasks_extract._needs_review_for_empty_output(
        batch={"metadata_json": {"high_value": True}},
        chunks=[{"text": "本页为空白模板，待填写。"}],
        usage=usage,
    )


def test_reference_only_zero_output_does_not_need_review() -> None:
    usage = BatchUsage(
        source_file="附件10.xlsx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"has_requirements": False, "suspected_missing": False, "empty_reason": "reference_only"},
    )

    assert not tasks_extract._needs_review_for_empty_output(
        batch={"metadata_json": {"high_value": True}},
        chunks=[{"text": "技术文件制作要求详见附件10。"}],
        usage=usage,
    )


def test_provider_limit_for_pro_max_is_one() -> None:
    limit = provider_limit_for(model="deepseek-v4-pro", reasoning_effort="max")

    assert limit.max_running == 1


def test_provider_limit_for_flash_allows_more_parallelism() -> None:
    limit = provider_limit_for(model="deepseek-v4-flash", reasoning_effort=None)

    assert limit.max_running == 4


def test_provider_limit_for_fast_prefilter_allows_more_parallelism() -> None:
    limit = provider_limit_for(
        model="deepseek-v4-flash",
        reasoning_effort=None,
        thinking_enabled=False,
        quality_policy="fast_prefilter",
    )

    assert limit.max_running == 6
    assert limit.quality_policy == "fast_prefilter"
    assert limit.thinking_enabled is False


def test_quality_policy_priority_orders_review_before_flash() -> None:
    assert tasks_extract._quality_policy_priority({"metadata_json": {"quality_policy": "pro_review"}}) == 0
    assert (
        tasks_extract._quality_policy_priority({"metadata_json": {"quality_policy": "table_or_critical_extract"}})
        == 1
    )
    assert tasks_extract._quality_policy_priority({"metadata_json": {"quality_policy": "flash_extract"}}) == 2
    assert tasks_extract._quality_policy_priority({"metadata_json": {"quality_policy": "fast_prefilter"}}) == 3


def test_backoff_only_applies_to_rate_or_transport_errors(monkeypatch) -> None:
    monkeypatch.setattr("tender_backend.services.extract_service.retry_policy.random.randint", lambda a, b: 0)

    assert backoff_countdown_seconds(
        retry_count=1,
        error_type="ReadTimeout",
        error_message="timeout",
    ) == 30
    assert backoff_countdown_seconds(
        retry_count=1,
        error_type="ValueError",
        error_message="bad json",
    ) == 0


def test_pro_review_batch_index_uses_offset() -> None:
    assert pro_review_batch_index(7) == 10_007


def test_retry_batch_index_uses_offset_and_parent_index() -> None:
    assert retry_batch_index(batch_index=7, part_index=2) == 20_702


def test_degraded_reasoning_effort_steps_down_max_then_high() -> None:
    assert degraded_reasoning_effort("max") == "high"
    assert degraded_reasoning_effort("high") is None
    assert degraded_reasoning_effort(None) is None


def test_split_chunk_ids_for_retry_splits_into_bounded_parts() -> None:
    parts = split_chunk_ids_for_retry(["a", "b", "c", "d", "e"], max_parts=3)

    assert parts == [["a", "b"], ["c", "d"], ["e"]]


def test_should_create_retry_batches_only_for_first_transport_failure() -> None:
    assert should_create_retry_batches(
        retry_count=0,
        metadata={},
        error_type="ReadTimeout",
        error_message="timeout",
    )
    assert not should_create_retry_batches(
        retry_count=1,
        metadata={},
        error_type="ReadTimeout",
        error_message="timeout",
    )
    assert not should_create_retry_batches(
        retry_count=0,
        metadata={"retry_of_batch_id": "parent"},
        error_type="ReadTimeout",
        error_message="timeout",
    )
    assert not should_create_retry_batches(
        retry_count=0,
        metadata={},
        error_type="ValueError",
        error_message="bad json",
    )


def test_build_review_metadata_marks_source_batch() -> None:
    usage = BatchUsage(
        source_file="招标文件.docx",
        chunks_in_batch=1,
        extracted=0,
        dropped_invalid=0,
        input_tokens=100,
        output_tokens=20,
        used_fallback=False,
        resolved_model="deepseek-v4-flash",
        latency_ms=1000,
        batch_quality={"suspected_missing": True},
    )

    metadata = tasks_extract._build_review_metadata(
        {
            "id": "batch-1",
            "model": "deepseek-v4-flash",
            "reasoning_effort": None,
            "metadata_json": {"classification": "tender_document"},
        },
        usage,
    )

    assert metadata["review_of_batch_id"] == "batch-1"
    assert metadata["review_reason"] == "empty_high_value_output"
    assert metadata["review_source_model"] == "deepseek-v4-flash"
    assert metadata["high_value"] is True
    assert metadata["task_type"] == "extract_tender_requirements"


def test_build_retry_batches_splits_and_degrades_effort() -> None:
    retry_batches = tasks_extract._build_retry_batches(
        {
            "id": "batch-1",
            "source_file": "招标文件.docx",
            "batch_index": 3,
            "chunk_ids_json": ["a", "b", "c", "d"],
            "chunk_count": 4,
            "input_char_count": 400,
            "estimated_input_tokens": 200,
            "model": "deepseek-v4-pro",
            "reasoning_effort": "max",
            "response_format": "json_object",
            "metadata_json": {"classification": "tender_document"},
        },
        error_type="ReadTimeout",
        error_message="timeout",
    )

    assert len(retry_batches) == 4
    assert retry_batches[0]["batch_index"] == 20_300
    assert retry_batches[0]["chunk_ids"] == ["a"]
    assert retry_batches[0]["reasoning_effort"] == "high"
    assert retry_batches[0]["metadata_json"]["retry_of_batch_id"] == "batch-1"
    assert retry_batches[0]["metadata_json"]["retry_strategy"] == "split_batch_and_degrade_effort"
    assert retry_batches[0]["metadata_json"]["task_type"] == "extract_tender_requirements"
    assert retry_batches[0]["metadata_json"]["stage"] == "retry"


def test_build_followup_batch_from_prefilter_creates_flash_extract_batch() -> None:
    followup = tasks_extract._build_followup_batch_from_prefilter(
        batch={
            "id": "batch-1",
            "source_file": "普通附件.docx",
            "batch_index": 2,
            "tender_document_file_id": "file-1",
            "input_char_count": 1200,
            "estimated_input_tokens": 600,
            "response_format": "json_object",
            "metadata_json": {
                "task_type": "extract_tender_requirements",
                "quality_policy": "fast_prefilter",
                "next_quality_policy": "flash_extract",
                "next_model": "deepseek-v4-flash",
                "next_reasoning_effort": None,
            },
        },
        candidate_chunks=[
            {"id": "chunk-a"},
            {"id": "chunk-b"},
        ],
        prefilter_stats={
            "original_chunk_count": 10,
            "candidate_chunk_count": 2,
            "prefilter_dropped_chunks": 8,
        },
    )

    assert followup is not None
    assert followup["batch_index"] == 50_002
    assert followup["model"] == "deepseek-v4-flash"
    assert followup["metadata_json"]["quality_policy"] == "flash_extract"
    assert followup["metadata_json"]["prefilter_of_batch_id"] == "batch-1"
    assert followup["metadata_json"]["prefilter_candidate_chunk_count"] == 2
    assert followup["metadata_json"]["task_type"] == "extract_tender_requirements"
    assert followup["metadata_json"]["stage"] == "followup"


def test_handle_batch_failure_creates_retry_batches_for_transport_errors(monkeypatch) -> None:
    scheduled: list[dict] = []

    class _Repo:
        def __init__(self) -> None:
            self.superseded = None
            self.failed = None

        def create_retry_batches(self, conn, *, source_batch, retry_batches):
            return [
                {"id": "retry-1"},
                {"id": "retry-2"},
            ]

        def mark_batch_superseded(self, conn, *, batch_id, metadata_json=None):
            self.superseded = {
                "batch_id": batch_id,
                "metadata_json": metadata_json,
            }
            return {"id": batch_id}

        def mark_batch_failed(self, conn, *, batch_id, error_type, error_message, retryable=True):
            self.failed = {
                "batch_id": batch_id,
                "error_type": error_type,
                "error_message": error_message,
                "retryable": retryable,
            }
            return {"id": batch_id}

        def refresh_run_progress(self, conn, *, run_id):
            return {"status": "running"}

    class _Conn:
        def __init__(self) -> None:
            self.committed = False

        def commit(self) -> None:
            self.committed = True

    monkeypatch.setattr(tasks_extract, "_ai_repo", _Repo())
    monkeypatch.setattr(tasks_extract, "_build_retry_batches", lambda batch, *, error_type, error_message: [
        {"id": "new-batch-1"},
        {"id": "new-batch-2"},
    ])
    monkeypatch.setattr(tasks_extract, "backoff_countdown_seconds", lambda **kwargs: 15)
    monkeypatch.setattr(
        tasks_extract.run_tender_ai_extraction_batch,
        "apply_async",
        lambda **kwargs: scheduled.append(kwargs),
    )

    conn = _Conn()
    result = tasks_extract._handle_batch_failure(
        conn=conn,
        batch={
            "id": "batch-1",
            "run_id": "run-1",
            "retry_count": 0,
            "max_retries": 2,
            "model": "deepseek-v4-flash",
            "reasoning_effort": None,
            "metadata_json": {},
        },
        batch_uuid="batch-1",
        batch_id="batch-1",
        error_type="HTTPStatusError",
        error_message="502 Bad Gateway: incomplete chunked read",
    )

    assert result == {"batch_id": "batch-1", "run_status": "running"}
    assert conn.committed is True
    assert tasks_extract._ai_repo.superseded is not None
    assert tasks_extract._ai_repo.superseded["metadata_json"]["retry_strategy"] == "split_batch_and_degrade_effort"
    assert tasks_extract._ai_repo.superseded["metadata_json"]["retry_error_message"].startswith("502 Bad Gateway")
    assert tasks_extract._ai_repo.failed is None
    assert scheduled == [
        {"kwargs": {"batch_id": "retry-1"}, "countdown": 15},
        {"kwargs": {"batch_id": "retry-2"}, "countdown": 15},
    ]


def test_run_batch_passes_conn_when_no_overrides_resolved(monkeypatch) -> None:
    batch_uuid = "11111111-1111-1111-1111-111111111111"
    run_uuid = "22222222-2222-2222-2222-222222222222"
    document_uuid = "33333333-3333-3333-3333-333333333333"
    chunk_uuid = "44444444-4444-4444-4444-444444444444"

    class _Conn:
        def commit(self) -> None:
            return None

    class _Pool:
        def __init__(self) -> None:
            self.conn = _Conn()

        class _Manager:
            def __init__(self, conn) -> None:
                self._conn = conn

            def __enter__(self):
                return self._conn

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        def connection(self):
            return self._Manager(self.conn)

    class _AiRepo:
        def mark_batch_running(self, conn, *, batch_id):
            return {
                "id": batch_uuid,
                "run_id": run_uuid,
                "tender_document_id": document_uuid,
                "chunk_ids_json": [chunk_uuid],
                "source_file": "招标文件.docx",
                "response_format": "json_object",
                "metadata_json": {},
                "batch_index": 1,
                "model": "deepseek-v4-flash",
                "reasoning_effort": None,
                "created_at": None,
                "started_at": None,
            }

        def get_run(self, conn, *, run_id):
            return {"id": run_uuid, "project_id": "proj-1", "status": "running"}

        def mark_batch_succeeded(self, conn, **kwargs):
            return None

        def refresh_run_progress(self, conn, *, run_id):
            return {"status": "running"}

        def mark_batch_failed(self, conn, **kwargs):
            raise AssertionError("worker should not enter failure path")

        def create_retry_batches(self, conn, *, source_batch, retry_batches):
            raise AssertionError("worker should not create retry batches")

        def mark_batch_superseded(self, conn, **kwargs):
            raise AssertionError("worker should not supersede batch")

    captured: dict[str, object] = {}

    async def _fake_extract_requirements_for_batch(chunks, **kwargs):
        captured["conn"] = kwargs.get("conn")
        captured["primary_override"] = kwargs.get("primary_override")
        captured["fallback_override"] = kwargs.get("fallback_override")
        return AiExtractionRunSummary(
            requirements=[],
            batches=[
                BatchUsage(
                    source_file="招标文件.docx",
                    chunks_in_batch=len(chunks),
                    extracted=0,
                    dropped_invalid=0,
                    input_tokens=0,
                    output_tokens=0,
                    used_fallback=False,
                    resolved_model="stub",
                    latency_ms=1,
                )
            ],
        )

    monkeypatch.setattr(tasks_extract, "get_settings", lambda: type("S", (), {"database_url": "postgresql://test"})())
    monkeypatch.setattr(tasks_extract, "get_pool", lambda database_url: _Pool())
    monkeypatch.setattr(tasks_extract, "_ai_repo", _AiRepo())
    monkeypatch.setattr(
        tasks_extract,
        "_doc_repo",
        type(
            "DocRepo",
            (),
            {
                "list_source_chunks": staticmethod(
                    lambda conn, tender_document_id: [
                        {"id": chunk_uuid, "sort_order": 1, "source_file": "招标文件.docx", "text": "测试条款"}
                    ]
                )
            },
        )(),
    )
    monkeypatch.setattr(tasks_extract, "_requirement_repo", type("ReqRepo", (), {"create_many": staticmethod(lambda *a, **k: [])})())
    monkeypatch.setattr(tasks_extract, "_provider_limit_countdown", lambda conn, batch: 0)
    monkeypatch.setattr(tasks_extract, "_resolve_batch_overrides", lambda conn, *, batch: (None, None))
    monkeypatch.setattr(tasks_extract, "_run_async", lambda coro: __import__("asyncio").run(coro))
    monkeypatch.setattr(tasks_extract, "extract_requirements_for_batch", _fake_extract_requirements_for_batch)

    result = tasks_extract.run_tender_ai_extraction_batch.run(batch_id=batch_uuid)

    assert result == {"batch_id": batch_uuid, "run_status": "running"}
    assert captured["conn"] is not None
    assert captured["primary_override"] is None
    assert captured["fallback_override"] is None
