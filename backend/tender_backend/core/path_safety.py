from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def ensure_path_within_root(value: str | Path, root: str | Path, *, label: str) -> Path:
    resolved = resolve_path(value)
    resolved_root = resolve_path(root)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{label} must be within {resolved_root}") from exc
    return resolved


def ensure_path_within_roots(value: str | Path, roots: Iterable[str | Path], *, label: str) -> Path:
    resolved = resolve_path(value)
    for root in roots:
        try:
            resolved.relative_to(resolve_path(root))
            return resolved
        except ValueError:
            continue
    raise ValueError(f"{label} is outside the configured allowed directories")


def parse_root_list(raw: str) -> list[Path]:
    return [resolve_path(part) for part in raw.split(os.pathsep) if part.strip()]
