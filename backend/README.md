# Backend

FastAPI business API for the tender system.

## Runtime Configuration

The backend reads settings from environment variables and an optional local `.env`.
The following variables are especially important for the template-package and master-data flows:

- `DATABASE_URL`
  - Required for the API to start.
  - Example: `postgresql://tender:change-me@localhost:5432/tender`
- `TEMPLATE_IMPORT_ROOTS`
  - Required for `POST /api/template-packages/import`.
  - Use a path-separated allowlist of directories the server may read template packages from.
  - Template packages are single-DOCX documents. Import may point to a `.docx` file or a directory containing exactly one `.docx` file.
  - On macOS/Linux use `:` as the separator.
  - Example: `/workspace/data/template_imports:/workspace/shared/template_packages`
- `EVIDENCE_UPLOAD_DIR`
  - Root directory for managed evidence asset uploads.
  - Uploaded files and any file paths referenced by evidence assets must stay under this directory.
  - Example: `/workspace/data/master_data_assets`
- `EVIDENCE_UPLOAD_MAX_BYTES`
  - Maximum allowed size for a single evidence upload.
  - Default: `52428800` (50 MiB)
- `TEMPLATE_RENDER_ROOT`
  - Output directory for single-item DOCX renders.
  - Default: `/tmp/tender_template_renders`
- `TEMPLATE_BUNDLE_ROOT`
  - Output directory for package bundle renders and zip archives.
  - Default: `/tmp/tender_template_bundles`

## Deployment Notes

- `TEMPLATE_IMPORT_ROOTS` should point only at curated, read-only directories. Do not set it to a broad parent like `/` or a user home directory.
- `EVIDENCE_UPLOAD_DIR`, `TEMPLATE_RENDER_ROOT`, and `TEMPLATE_BUNDLE_ROOT` should be backed by writable storage with enough capacity for large attachments and bundle exports.
- If you run multiple backend workers, prefer a shared persistent volume for `EVIDENCE_UPLOAD_DIR`. Render roots may stay on fast ephemeral storage if bundles are short-lived.
- Keep import roots and upload roots separate. Imported template packages are treated as trusted read sources; uploaded evidence assets are managed application data.

## Chapter Generation

### Production Flow

All production chapter generation should use the API flow:

```bash
curl -X POST http://localhost:8000/api/projects/{project_id}/chapters/{chapter_id}/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"target_pages": 100}'
```

Long technical chapters automatically route through the longform generation path
and produce quality evidence used by export gates.

### Non-Production Debug Flow

`scripts/generate_sgcc_chapters_docx.py` remains available only for offline
prompt debugging. It bypasses longform quality gates and must not be treated as
production output.
