"""Shared helpers for FastAPI ``UploadFile`` handling."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

UPLOAD_CHUNK_SIZE = 1024 * 1024


async def read_upload_with_limit(file: UploadFile, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"file exceeds {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)
