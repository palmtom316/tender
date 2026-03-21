from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import fastapi.concurrency
import fastapi.dependencies.utils
import fastapi.routing
import starlette._exception_handler
import starlette.background
import starlette.concurrency
import starlette.datastructures
import starlette.endpoints
import starlette.middleware.errors
import starlette.routing

_EXECUTOR = ThreadPoolExecutor(max_workers=32, thread_name_prefix="tender-sync")
_PATCHED = False


async def _run_in_explicit_threadpool(func: Any, *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    bound = partial(ctx.run, partial(func, *args, **kwargs))
    return await loop.run_in_executor(_EXECUTOR, bound)


def apply_threadpool_compat() -> None:
    global _PATCHED
    if _PATCHED:
        return

    patched_modules = (
        starlette.concurrency,
        starlette.routing,
        starlette.datastructures,
        starlette._exception_handler,
        starlette.endpoints,
        starlette.middleware.errors,
        starlette.background,
        fastapi.concurrency,
        fastapi.routing,
        fastapi.dependencies.utils,
    )

    for module in patched_modules:
        setattr(module, "run_in_threadpool", _run_in_explicit_threadpool)

    _PATCHED = True
