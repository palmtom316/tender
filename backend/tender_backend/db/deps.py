from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException
from psycopg import Connection

from tender_backend.core.config import Settings, get_settings
from tender_backend.db.pool import get_pool


def get_db_conn(settings: Settings = Depends(get_settings)) -> Generator[Connection, None, None]:
    if not settings.database_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL is not configured")

    pool = get_pool(database_url=settings.database_url)
    with pool.connection() as conn:
        yield conn
