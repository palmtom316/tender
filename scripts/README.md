# Scripts Directory

## Production / Governance Scripts

- `check_acceptance_before_test.sh`
  - Chapter 8 e2e 前置门控
  - 若 acceptance 文档或真实样本证据缺失，直接失败
- `run_chapter_8_acceptance.py`
  - 采集 chapter 8 acceptance 证据
  - 输出 `chapter_draft` / `export_gate` / latest `export_record` 快照

## Development / Debug Scripts

- `generate_sgcc_chapters_docx.py`
  - **仅用于离线提示词调试**
  - **不是生产链路**
  - 会绕过 longform 生成闭环与 export quality gates

## Production Chapter Generation

正式生成章节请走主 API：

```bash
POST /api/projects/{project_id}/chapters/{chapter_id}/generate
```

对于长技术章（例如第 8 章且 `target_pages >= 80`），系统会自动进入：

- `LongformSectionGenerator`
- `coverage_report`
- `chart_closure_report`
- `export_gate`

不要再用离线脚本产物充当正式交付样本。
