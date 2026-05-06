from __future__ import annotations

from tender_backend.core.config import get_settings


def ai_gateway_headers() -> dict[str, str]:
    secret = get_settings().ai_gateway_shared_secret
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}"}
