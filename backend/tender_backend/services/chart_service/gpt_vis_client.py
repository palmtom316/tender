"""GPT-Vis-SSR HTTP client (skeleton).

Calls a privately deployed gpt-vis-ssr wrapper service exposing
`POST /render` with body `{type, data, theme?}` and response
`{success, svg, errorMessage}` (contract sketched in
docs/plans/2026-05-18-gpt-vis-ssr-research.md §5).

When `CHART_GPT_VIS_URL` is unset, render() returns None so the caller
can fall back to the next engine in the strategy chain. This lets us
land the multi-engine dispatch code (T8) before the actual container is
deployed (T7).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from tender_backend.core.config import get_settings


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
    timeout = settings.chart_gpt_vis_timeout_seconds
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/render",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("success"):
        return None
    svg = data.get("svg")
    if isinstance(svg, str) and svg.lstrip().startswith("<svg"):
        return svg
    return None
