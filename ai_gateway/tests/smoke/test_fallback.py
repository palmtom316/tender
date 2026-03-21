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
            default_primary_model="deepseek-chat",
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
    assert captured["timeout"] == 180
    assert captured["max_retries"] == 0
