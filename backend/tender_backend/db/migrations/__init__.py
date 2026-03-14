from __future__ import annotations

from pathlib import Path


def load_initial_schema_sql() -> str:
    return (Path(__file__).resolve().parent / "0001_initial_schema.sql").read_text(encoding="utf-8")

