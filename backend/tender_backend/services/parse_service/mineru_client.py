"""MinerU v4 batch API client.

Contract:
- POST `/file-urls/batch` — request signed upload URLs, returns `batch_id` +
  one signed URL per file.
- PUT the raw PDF bytes to the signed URL. MinerU kicks off parsing once the
  upload completes.
- GET `/extract-results/batch/{batch_id}` — poll until `state == "done"`,
  then download `full_zip_url` which contains `full.md` plus a structured JSON
  payload with `pdf_info` (commonly `*_middle.json`, sometimes `layout.json`).

`MineruParseResult` carries the canonical `normalize_mineru_payload` output
(`parser_version`, `pages`, `tables`, `full_markdown`) so downstream code
never has to probe provider shapes.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from zipfile import ZipFile

import httpx
import structlog

from tender_backend.services.parse_service.mineru_normalizer import normalize_mineru_payload

logger = structlog.stdlib.get_logger(__name__)

MINERU_BASE_URL = os.environ.get("MINERU_API_URL", "https://mineru.net/api/v4/extract/task")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")

_API_ROOT_SUFFIXES = ("/extract/task", "/parse")


def _extract_mineru_token_value(api_key: str) -> str:
    """Derive the extra MinerU `token` header from the configured API key."""
    normalized = str(api_key or "").strip()
    if not normalized:
        return ""

    parts = normalized.split(".")
    if len(parts) == 3:
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except (ValueError, TypeError, json.JSONDecodeError):
            claims = None
        if isinstance(claims, dict):
            for key in ("uuid", "clientId", "phone", "jti"):
                value = str(claims.get(key) or "").strip()
                if value:
                    return value

    return normalized


def build_mineru_auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    token_value = _extract_mineru_token_value(api_key)
    if token_value:
        headers["token"] = token_value
    return headers


@dataclass(frozen=True)
class MineruUploadInfo:
    batch_id: str
    upload_url: str
    data_id: str


@dataclass(frozen=True)
class MineruRequestOptions:
    """v4 batch-request knobs exposed through `/file-urls/batch`.

    Maps 1:1 to the documented request body:
    - `model_version`, `language`, `enable_table`, `enable_formula` → top-level
    - `is_ocr`, `page_ranges` → per-file fields (inside `files[]`)
    """

    model_version: str = "vlm"
    language: str = "ch"
    enable_table: bool = True
    enable_formula: bool = False
    is_ocr: bool = True
    page_ranges: str | None = None


@dataclass(frozen=True)
class MineruParseResult:
    job_id: str  # == batch_id in v4
    status: str  # processing | completed | failed
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    raw_payload: dict[str, Any]
    extracted_pages: int | None = None
    total_pages: int | None = None


def _api_root(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    for suffix in _API_ROOT_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].rstrip("/")
    return normalized


def _default_options() -> MineruRequestOptions:
    """Build a `MineruRequestOptions` from application settings.

    Imported lazily so the client module doesn't pin a settings singleton at
    import time — handy for tests that construct the client before settings
    are finalised.
    """
    from tender_backend.core.config import get_settings

    settings = get_settings()
    return MineruRequestOptions(
        model_version=settings.standard_mineru_model_version,
        language=settings.standard_mineru_language,
        enable_table=settings.standard_mineru_enable_table,
        enable_formula=settings.standard_mineru_enable_formula,
        is_ocr=settings.standard_mineru_is_ocr,
        page_ranges=settings.standard_mineru_page_ranges,
    )


def _progress_from_item(item: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (extracted_pages, total_pages) from a running extract_result item.

    The v4 API exposes progress on `item.extract_progress` when the task is
    in `state=running`; silently absent for other states.
    """
    progress = item.get("extract_progress")
    if not isinstance(progress, dict):
        return None, None
    extracted = progress.get("extracted_pages")
    total = progress.get("total_pages")
    return (
        extracted if isinstance(extracted, int) else None,
        total if isinstance(total, int) else None,
    )


def _normalize_from_zip(content: bytes) -> dict[str, Any]:
    """Extract `full.md` plus the canonical `pdf_info` JSON from a MinerU zip.

    Raises RuntimeError when the zip is missing any structured JSON payload
    carrying the canonical `pdf_info` array.
    """
    with ZipFile(BytesIO(content)) as zf:
        names = zf.namelist()

        md_content = ""
        for candidate in ("full.md", "result/full.md", "output/full.md"):
            if candidate in names:
                md_content = zf.read(candidate).decode("utf-8")
                break
        if not md_content:
            for name in names:
                if name.endswith(".md"):
                    md_content = zf.read(name).decode("utf-8")
                    break

        middle_json: dict[str, Any] | None = None
        json_candidates = [name for name in names if name.endswith("_middle.json")]
        if not json_candidates:
            json_candidates = [name for name in names if name.endswith(".json")]
        for name in json_candidates:
            try:
                payload = json.loads(zf.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and isinstance(payload.get("pdf_info"), list):
                middle_json = payload
                break
        if middle_json is None:
            raise RuntimeError(
                "MinerU result zip does not contain a structured JSON payload with pdf_info; "
                "the v4 batch contract requires a canonical MinerU payload such as layout.json or *_middle.json."
            )

    if md_content and "full_markdown" not in middle_json:
        middle_json["full_markdown"] = md_content
    return normalize_mineru_payload(middle_json)


class MineruClient:
    def __init__(
        self,
        *,
        base_url: str = MINERU_BASE_URL,
        api_key: str = MINERU_API_KEY,
        options: MineruRequestOptions | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_root = _api_root(base_url)
        self._headers = build_mineru_auth_headers(api_key)
        self._options = options if options is not None else _default_options()
        self._timeout = timeout
        self._transport = transport

    def _async_client(self, *, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout if timeout is not None else self._timeout,
            transport=self._transport,
        )

    async def request_upload_url(
        self,
        filename: str,
        *,
        data_id: str,
    ) -> MineruUploadInfo:
        """POST `/file-urls/batch` — returns `batch_id` + a single signed URL."""
        opts = self._options
        file_obj: dict[str, Any] = {
            "name": filename,
            "data_id": data_id,
            "is_ocr": opts.is_ocr,
        }
        if opts.page_ranges:
            file_obj["page_ranges"] = opts.page_ranges
        body: dict[str, Any] = {
            "files": [file_obj],
            "model_version": opts.model_version,
            "language": opts.language,
            "enable_table": opts.enable_table,
            "enable_formula": opts.enable_formula,
        }
        async with self._async_client() as client:
            resp = await client.post(
                f"{self._api_root}/file-urls/batch",
                json=body,
                headers=self._headers,
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}

        batch_id = data.get("batch_id")
        urls = data.get("file_urls") or []
        if not batch_id or not urls:
            raise RuntimeError(f"MinerU did not return batch_id/upload URL: {data!r}")
        return MineruUploadInfo(
            batch_id=str(batch_id),
            upload_url=str(urls[0]),
            data_id=data_id,
        )

    async def upload_file(
        self,
        upload_url: str,
        content: bytes,
        content_type: str | None = None,
    ) -> None:
        """PUT the raw file bytes to the pre-signed upload URL."""
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        async with self._async_client(timeout=120.0) as client:
            resp = await client.put(upload_url, content=content, headers=headers)
            resp.raise_for_status()

    async def get_parse_status(self, batch_id: str) -> MineruParseResult:
        """GET `/extract-results/batch/{batch_id}` and normalize once done."""
        async with self._async_client() as client:
            resp = await client.get(
                f"{self._api_root}/extract-results/batch/{batch_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}

        items = data.get("extract_result") or []
        if not items:
            return MineruParseResult(
                job_id=batch_id,
                status="processing",
                pages=[],
                tables=[],
                sections=[],
                raw_payload={},
            )

        item = items[0]
        state = (item.get("state") or item.get("status") or "").lower()

        if state in ("done", "completed", "success"):
            zip_url = (
                item.get("full_zip_url")
                or item.get("result_zip_url")
                or item.get("zip_url")
            )
            if not zip_url:
                raise RuntimeError(f"MinerU did not return a zip URL: {item!r}")
            async with self._async_client(timeout=60.0) as client:
                zip_resp = await client.get(zip_url)
                zip_resp.raise_for_status()
            normalized = _normalize_from_zip(zip_resp.content)
            return MineruParseResult(
                job_id=batch_id,
                status="completed",
                pages=normalized["pages"],
                tables=normalized["tables"],
                sections=[],
                raw_payload=normalized,
            )

        if state in ("failed", "error"):
            return MineruParseResult(
                job_id=batch_id,
                status="failed",
                pages=[],
                tables=[],
                sections=[],
                raw_payload={"error": item.get("err_msg") or item.get("error")},
            )

        # Still queued/uploading/running — surface any progress counters the
        # server reports (`extract_progress.{extracted_pages, total_pages}`)
        # so callers can render "N/M pages" without a second API call.
        extracted_pages, total_pages = _progress_from_item(item)
        return MineruParseResult(
            job_id=batch_id,
            status="processing",
            pages=[],
            tables=[],
            sections=[],
            raw_payload={},
            extracted_pages=extracted_pages,
            total_pages=total_pages,
        )
