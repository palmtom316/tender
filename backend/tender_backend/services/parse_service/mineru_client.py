"""MinerU v4 batch API client.

Contract:
- POST `/file-urls/batch` — request signed upload URLs, returns `batch_id` +
  one signed URL per file.
- PUT the raw PDF bytes to the signed URL. MinerU kicks off parsing once the
  upload completes.
- GET `/extract-results/batch/{batch_id}` — poll until `state == "done"`,
  then download `full_zip_url` which contains `full.md` + `*_middle.json`.

`MineruParseResult` carries the canonical `normalize_mineru_payload` output
(`parser_version`, `pages`, `tables`, `full_markdown`) so downstream code
never has to probe provider shapes.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class MineruUploadInfo:
    batch_id: str
    upload_url: str
    data_id: str


@dataclass(frozen=True)
class MineruParseResult:
    job_id: str  # == batch_id in v4
    status: str  # processing | completed | failed
    pages: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    raw_payload: dict[str, Any]


def _api_root(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    for suffix in _API_ROOT_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)].rstrip("/")
    return normalized


def _normalize_from_zip(content: bytes) -> dict[str, Any]:
    """Extract `full.md` + `*_middle.json` from a MinerU result zip and run
    the canonical normalizer against the middle.json.

    Raises RuntimeError when the zip is missing the canonical pdf_info payload.
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
                "MinerU result zip does not contain a *_middle.json payload; "
                "the v4 batch contract requires the canonical pdf_info structure."
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
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_root = _api_root(base_url)
        self._headers = {"Authorization": f"Bearer {api_key}"}
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
        is_ocr: bool = True,
    ) -> MineruUploadInfo:
        """POST `/file-urls/batch` — returns `batch_id` + a single signed URL."""
        body = {
            "files": [
                {
                    "name": filename,
                    "data_id": data_id,
                    "is_ocr": is_ocr,
                }
            ],
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

        return MineruParseResult(
            job_id=batch_id,
            status="processing",
            pages=[],
            tables=[],
            sections=[],
            raw_payload={},
        )
