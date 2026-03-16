"""MinerU Commercial API client.

Handles: request upload URL, backend-direct upload, submit parse,
poll result, and normalize output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

logger = structlog.stdlib.get_logger(__name__)

MINERU_BASE_URL = os.environ.get("MINERU_API_URL", "https://mineru.example.com/api/v1")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")


@dataclass(frozen=True)
class MineruUploadInfo:
    upload_url: str
    file_key: str


@dataclass(frozen=True)
class MineruParseResult:
    job_id: str
    status: str  # processing | completed | failed
    pages: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    tables: list[dict[str, Any]]


class MineruClient:
    def __init__(
        self,
        *,
        base_url: str = MINERU_BASE_URL,
        api_key: str = MINERU_API_KEY,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._timeout = timeout

    async def request_upload_url(self, filename: str) -> MineruUploadInfo:
        """Get a pre-signed upload URL from MinerU."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/files/upload-url",
                json={"filename": filename},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return MineruUploadInfo(
            upload_url=data["upload_url"],
            file_key=data["file_key"],
        )

    async def upload_file(self, upload_url: str, content: bytes, content_type: str) -> None:
        """Upload file content to the pre-signed URL."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.put(
                upload_url,
                content=content,
                headers={"Content-Type": content_type},
            )
            resp.raise_for_status()

    async def submit_parse(self, file_key: str) -> str:
        """Submit a parse request and return the MinerU job ID."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/parse",
                json={"file_key": file_key},
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["job_id"]

    async def get_parse_status(self, job_id: str) -> MineruParseResult:
        """Poll the parse result for a given job."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base_url}/parse/{job_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return MineruParseResult(
            job_id=job_id,
            status=data.get("status", "processing"),
            pages=data.get("pages", []),
            sections=data.get("sections", []),
            tables=data.get("tables", []),
        )
