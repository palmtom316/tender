from __future__ import annotations

import asyncio
from typing import Any

import httpx
from httpx import ASGITransport, Response


class SyncASGIClient:
    def __init__(self, app: Any, *, base_url: str = "http://testserver") -> None:
        self.app = app
        self.base_url = base_url
        self.headers: dict[str, str] = {}

    async def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        headers = {**self.headers, **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url=self.base_url,
            headers=headers,
        ) as client:
            return await client.request(method, url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> Response:
        return asyncio.run(self._request(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        return None
