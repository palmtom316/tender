"""Repository for prompt_template table."""

from __future__ import annotations

from tender_backend.services.prompt_service import PromptService

# Re-export: the PromptService already handles prompt_template CRUD.
# This module exists for consistency with the repository pattern.
prompt_repo = PromptService()
