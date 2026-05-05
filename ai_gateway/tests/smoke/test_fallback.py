from types import SimpleNamespace

from tender_ai_gateway import fallback


def test_call_with_fallback_uses_task_level_timeout_and_retries(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, max_retries) -> None:
            captured["timeout"] = timeout
            captured["max_retries"] = max_retries
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
            message = SimpleNamespace(content="[]")
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice], usage=usage)

    monkeypatch.setattr(fallback, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    result = fallback.call_with_fallback(
        task_type="tag_clauses",
        messages=[{"role": "user", "content": "test"}],
    )

    assert result.content == "[]"
    assert captured["timeout"] == 600
    assert captured["max_retries"] == 0


def test_call_with_fallback_uses_task_profile_max_tokens(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, max_retries) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured["max_tokens"] = kwargs["max_tokens"]
            usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
            message = SimpleNamespace(content="[]")
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice], usage=usage)

    monkeypatch.setattr(fallback, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    fallback.call_with_fallback(
        task_type="tag_clauses",
        messages=[{"role": "user", "content": "test"}],
        max_tokens=None,
    )

    assert captured["max_tokens"] == 32768


def test_call_with_fallback_rejects_deepseek_v4_pro_override(monkeypatch) -> None:
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    try:
        fallback.call_with_fallback(
            task_type="tag_clauses",
            messages=[{"role": "user", "content": "test"}],
            primary_override=SimpleNamespace(
                base_url="https://api.deepseek.com/v1",
                api_key="deepseek-key",
                model="deepseek-v4-pro",
                extra_body=None,
            ),
        )
    except ValueError as exc:
        assert "deepseek-v4-pro is disabled" in str(exc)
    else:
        raise AssertionError("deepseek-v4-pro override should be rejected for non-tender tasks")


def test_call_with_fallback_allows_v4_pro_for_tender_extraction(monkeypatch) -> None:
    """Tender extraction tasks are whitelisted to use deepseek-v4-pro."""
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, max_retries) -> None:
            captured["model_base_url"] = base_url
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured["model"] = kwargs["model"]
            captured["max_tokens"] = kwargs["max_tokens"]
            captured["extra_body"] = kwargs.get("extra_body")
            usage = SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=20,
                prompt_cache_hit_tokens=4,
                prompt_cache_miss_tokens=6,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=3),
            )
            message = SimpleNamespace(content="[]")
            choice = SimpleNamespace(message=message, finish_reason="stop")
            return SimpleNamespace(choices=[choice], usage=usage)

    monkeypatch.setattr(fallback, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    result = fallback.call_with_fallback(
        task_type="extract_tender_requirements",
        messages=[{"role": "user", "content": "test"}],
        primary_override=SimpleNamespace(
            base_url="https://api.deepseek.com/v1",
            api_key="deepseek-key",
            model="deepseek-v4-pro",
            extra_body={"reasoning_effort": "max"},
        ),
    )

    assert result.content == "[]"
    assert captured["model"] == "deepseek-v4-pro"
    assert captured["max_tokens"] == 65536
    assert captured["extra_body"] == {"reasoning_effort": "max"}
    assert result.finish_reason == "stop"
    assert result.prompt_cache_hit_tokens == 4
    assert result.prompt_cache_miss_tokens == 6
    assert result.reasoning_tokens == 3


def test_call_with_fallback_forwards_request_extra_body(monkeypatch) -> None:
    """`extra_body` passed at the call level reaches the OpenAI client."""
    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, max_retries) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured["extra_body"] = kwargs.get("extra_body")
            usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1)
            choice = SimpleNamespace(message=SimpleNamespace(content="ok"))
            return SimpleNamespace(choices=[choice], usage=usage)

    monkeypatch.setattr(fallback, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    fallback.call_with_fallback(
        task_type="tag_clauses",
        messages=[{"role": "user", "content": "test"}],
        extra_body={"reasoning_effort": "high"},
    )

    assert captured["extra_body"] == {"reasoning_effort": "high"}


def test_call_with_fallback_forwards_response_format_and_stream(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeChunk:
        choices = [SimpleNamespace(delta=SimpleNamespace(content="[]"), finish_reason="stop")]

    class _FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout, max_retries) -> None:
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            captured["response_format"] = kwargs.get("response_format")
            captured["stream"] = kwargs.get("stream")
            return iter([_FakeChunk()])

    monkeypatch.setattr(fallback, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(
        fallback,
        "get_settings",
        lambda: SimpleNamespace(
            default_primary_model="deepseek-v4-flash",
            default_fallback_model="qwen-max",
            deepseek_base_url="https://api.deepseek.com/v1",
            deepseek_api_key="deepseek-key",
            qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            qwen_api_key="qwen-key",
            default_timeout=60,
            default_retry_count=2,
        ),
    )

    result = fallback.call_with_fallback(
        task_type="extract_tender_requirements",
        messages=[{"role": "user", "content": "test"}],
        response_format={"type": "json_object"},
        stream=True,
    )

    assert result.content == "[]"
    assert result.finish_reason == "stop"
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["stream"] is True
