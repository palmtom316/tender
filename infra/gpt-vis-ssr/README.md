# GPT-Vis-SSR Wrapper

This directory contains the project-owned HTTP wrapper for `@antv/gpt-vis-ssr`.
The upstream package is a Node library, not a standalone HTTP service, so the
wrapper exposes the contract expected by the Python chart renderer.

## API

- `GET /health` returns status, concurrency settings, timeout, and supported types.
- `POST /render` accepts `{ "type": "...", "data": {...}, "theme": "default" }`.
- Successful renders return `{ "success": true, "svg": "<svg...>", "errorMessage": "" }`.
- Invalid input returns HTTP 400. Render failures return HTTP 200 with `success: false`
  so the Python caller can fall back to mermaid/native rendering.

`@antv/gpt-vis-ssr@0.3.7` exports PNG buffers, not native SVG. The wrapper
therefore returns an SVG shell with an embedded `data:image/png;base64,...`
payload plus `<title>/<desc>` text. This keeps the backend contract stable, but
the result is raster content inside SVG rather than true vector SVG.

## Supported Types

The wrapper is intentionally scoped to the chart families used by the POC:

- `flow-diagram`
- `network-graph`
- `organization-chart`
- `mindmap`
- `fishbone-diagram`
- `table`
- `summary`

`schedule_gantt` and `critical_path` remain on the mermaid/native path because
GPT-Vis does not provide a native Gantt renderer.
