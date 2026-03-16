"""Synonym loader — loads and validates synonym dictionary."""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.stdlib.get_logger(__name__)


def load_synonyms(path: str | Path) -> list[list[str]]:
    """Load synonyms from file, returning list of synonym groups."""
    path = Path(path)
    if not path.exists():
        logger.warning("synonyms_file_not_found", path=str(path))
        return []

    groups: list[list[str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        terms = [t.strip() for t in line.split(",") if t.strip()]
        if len(terms) >= 2:
            groups.append(terms)

    logger.info("synonyms_loaded", count=len(groups), path=str(path))
    return groups


def count_synonyms(path: str | Path) -> int:
    """Count the number of synonym entries in the file."""
    return len(load_synonyms(path))
