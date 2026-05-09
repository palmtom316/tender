from __future__ import annotations

from pathlib import Path

import fitz


def svg_to_png(svg: str, output_path: Path, *, zoom: float = 2.0) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open(stream=svg.encode("utf-8"), filetype="svg")
    page = document[0]
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    pixmap.save(str(output_path))
    document.close()
    return output_path
