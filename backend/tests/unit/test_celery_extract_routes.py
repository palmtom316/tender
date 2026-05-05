from tender_backend.workers.celery_app import app
from tender_backend.workers import tasks_extract
from tender_backend.services.extract_service.ai_requirements_extractor import BatchUsage
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
