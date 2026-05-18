from __future__ import annotations

import concurrent.futures
import os
import re
import time

import pytest

from tender_backend.services.chart_service.gpt_vis_client import GptVisClient


def _base_url() -> str:
    return os.getenv("GPT_VIS_CONTRACT_BASE_URL", "http://127.0.0.1:7102")


@pytest.fixture(scope="module")
def client() -> GptVisClient:
    candidate = GptVisClient(_base_url(), timeout_seconds=5.0)
    try:
        candidate.health()
    except candidate.ServiceUnavailable as exc:
        pytest.skip(f"gpt-vis-ssr is not available at {_base_url()}: {exc}")
    except candidate.Timeout as exc:
        pytest.skip(f"gpt-vis-ssr health check timed out at {_base_url()}: {exc}")
    return candidate


def _flow_payload(label: str = "起点") -> dict:
    return {
        "type": "flow-diagram",
        "data": {
            "title": "施工流程",
            "nodes": [
                {"name": "a", "label": label},
                {"name": "b", "label": "复核"},
            ],
            "edges": [{"source": "a", "target": "b", "name": "完成后"}],
        },
    }


def test_basic_render_returns_valid_svg(client: GptVisClient) -> None:
    svg = client.render(_flow_payload())

    assert svg.lstrip().startswith("<svg")


def test_svg_fits_a4_aspect(client: GptVisClient) -> None:
    svg = client.render(_flow_payload())
    width, height = _svg_dimensions(svg)

    assert 0.6 <= width / height <= 1.5


def test_chinese_font_rendering(client: GptVisClient) -> None:
    svg = client.render(_flow_payload("中文节点"))

    assert "中文节点" in svg


def test_invalid_spec_returns_4xx(client: GptVisClient) -> None:
    with pytest.raises(client.BadRequest):
        client.render({"type": "unknown", "data": {"nonsense": True}})


def test_timeout_handling(client: GptVisClient) -> None:
    short_timeout_client = GptVisClient(_base_url(), timeout_seconds=0.001)
    with pytest.raises((client.Timeout, client.ServiceUnavailable)):
        short_timeout_client.render(_flow_payload())


def test_offline_render_no_external_egress(client: GptVisClient) -> None:
    svg = client.render(_flow_payload())

    assert svg.lstrip().startswith("<svg")
    assert "http://" not in svg
    assert "https://" not in svg
    assert "data:image/png;base64," in svg


def test_concurrency_10_under_30s(client: GptVisClient) -> None:
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: client.render(_flow_payload()), range(10)))

    assert all(svg.lstrip().startswith("<svg") for svg in results)
    assert time.time() - start < 30


def _svg_dimensions(svg: str) -> tuple[float, float]:
    viewbox = re.search(r"viewBox=['\"]\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)", svg)
    if viewbox:
        return float(viewbox.group(1)), float(viewbox.group(2))
    width = re.search(r"\bwidth=['\"]([\d.]+)", svg)
    height = re.search(r"\bheight=['\"]([\d.]+)", svg)
    if width and height:
        return float(width.group(1)), float(height.group(1))
    pytest.fail("SVG lacks viewBox or width/height dimensions")
