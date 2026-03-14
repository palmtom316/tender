from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool


@dataclass(frozen=True)
class PoolConfig:
    database_url: str
    min_size: int = 1
    max_size: int = 5


_pool: ConnectionPool | None = None
_pool_config: PoolConfig | None = None


def get_pool(*, database_url: str) -> ConnectionPool:
    global _pool, _pool_config

    cfg = PoolConfig(database_url=database_url)
    if _pool is None or _pool_config != cfg:
        if _pool is not None:
            _pool.close()
        _pool = ConnectionPool(
            conninfo=database_url,
            min_size=cfg.min_size,
            max_size=cfg.max_size,
            open=True,
        )
        _pool_config = cfg

    return _pool


def close_pool() -> None:
    global _pool, _pool_config
    if _pool is None:
        return
    _pool.close()
    _pool = None
    _pool_config = None

