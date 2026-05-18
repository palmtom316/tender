"""GPT-Vis-SSR HTTP client.

Calls a privately deployed gpt-vis-ssr wrapper service exposing
`POST /render` with body `{type, data, theme?}` and response
`{success, svg, errorMessage}` (contract sketched in
docs/plans/2026-05-18-gpt-vis-ssr-research.md §5).

`GptVisClient.render()` raises typed exceptions for contract tests and
callers that need diagnostics. `render_via_gpt_vis()` is the production
adapter used by renderers.py; it intentionally returns None on any
failure so the strategy chain can fall back to mermaid/native rendering.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tender_backend.core.config import get_settings


class GptVisError(RuntimeError):
    """Base exception for GPT-Vis-SSR client failures."""


class BadRequest(GptVisError):
    """The wrapper rejected the payload as invalid."""


class RenderFailed(GptVisError):
    """The wrapper accepted the request but could not render SVG."""


class Timeout(GptVisError):
    """The wrapper did not respond inside the configured timeout."""


class ServiceUnavailable(GptVisError):
    """The wrapper is unavailable or returned an unexpected response."""


class GptVisClient:
    BadRequest = BadRequest
    RenderFailed = RenderFailed
    Timeout = Timeout
    ServiceUnavailable = ServiceUnavailable

    def __init__(self, base_url: str, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise Timeout("gpt-vis-ssr health check timed out") from exc
        except (urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            raise ServiceUnavailable("gpt-vis-ssr health check failed") from exc
        if not isinstance(data, dict):
            raise ServiceUnavailable("gpt-vis-ssr health check returned non-object JSON")
        return data

    def render(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/render",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise Timeout("gpt-vis-ssr render timed out") from exc
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise BadRequest(_http_error_message(exc)) from exc
            raise ServiceUnavailable(_http_error_message(exc)) from exc
        except (urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            raise ServiceUnavailable("gpt-vis-ssr render request failed") from exc

        if not isinstance(data, dict):
            raise ServiceUnavailable("gpt-vis-ssr returned non-object JSON")
        if not data.get("success"):
            raise RenderFailed(str(data.get("errorMessage") or "gpt-vis-ssr render failed"))
        svg = data.get("svg")
        if not isinstance(svg, str) or not svg.lstrip().startswith("<svg"):
            raise RenderFailed("gpt-vis-ssr returned missing or invalid SVG")
        return svg


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        body = ""
    if body:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body
        if isinstance(data, dict) and data.get("errorMessage"):
            return str(data["errorMessage"])
    return f"gpt-vis-ssr HTTP {exc.code}"


def render_via_gpt_vis(payload: dict[str, Any]) -> str | None:
    """Render a chart spec via the gpt-vis-ssr wrapper.

    Returns SVG text on success. Returns None when:
    - CHART_GPT_VIS_URL is unset (service not deployed yet)
    - HTTP / network / parse error
    - service responds with success=false or missing svg
    """
    settings = get_settings()
    base_url = settings.chart_gpt_vis_url
    if not base_url:
        return None
    try:
        return GptVisClient(base_url, settings.chart_gpt_vis_timeout_seconds).render(payload)
    except GptVisError:
        return None
