from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from tender_backend.workflows.generate_section import LLMGenerateSection, SaveDraft
from tender_backend.workflows.states import StepState


class _Ctx:
    def __init__(self):
        self.project_id = uuid4()
        self.data = {"_db_conn": object(), "chapter_id": uuid4(), "created_by": "Tester"}


def test_llm_generate_section_uses_technical_bid_writer(monkeypatch):
    ctx = _Ctx()
    calls = {}

    class _Writer:
        def generate_chapter(self, conn, *, project_id, chapter_id, created_by=None, rewrite_note=None):
            calls["conn"] = conn
            calls["project_id"] = project_id
            calls["chapter_id"] = chapter_id
            return {
                "draft": {"id": uuid4(), "content_md": "# 10.1 质量保证措施\n## 质量目标响应"},
                "run": {"id": uuid4()},
            }

    monkeypatch.setattr("tender_backend.workflows.generate_section.TechnicalBidWriter", _Writer)

    result = asyncio.run(LLMGenerateSection().execute(ctx))

    assert result.state == StepState.COMPLETED
    assert "正文内容占位符" not in ctx.data["generated_content"]
    assert calls["project_id"] == ctx.project_id
    assert isinstance(calls["chapter_id"], UUID)


def test_save_draft_noops_after_writer_persisted_draft(monkeypatch):
    ctx = _Ctx()
    ctx.data["generated_draft"] = {"id": uuid4(), "chapter_code": "10.1"}

    result = asyncio.run(SaveDraft().execute(ctx))

    assert result.state == StepState.COMPLETED
    assert "already saved" in result.message
