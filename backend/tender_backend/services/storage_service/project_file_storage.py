from __future__ import annotations

from pathlib import Path


class ProjectFileStorage:
    """Resolve and manage project_file storage keys.

    Today the codebase stores two shapes of keys:
    - local absolute paths for standard PDFs uploaded into the local standards volume
    - object-storage style keys such as `tender-raw/...` for generic project files

    Centralizing this check keeps API/workflow code from hard-coding filesystem
    assumptions, while still supporting the current local-standard-PDF flow.
    """

    def resolve_local_path(self, storage_key: str | None) -> Path | None:
        if not storage_key:
            return None

        candidate = Path(storage_key)
        if not candidate.is_absolute():
            return None
        if not candidate.is_file():
            return None
        return candidate

    def delete_managed_file(self, storage_key: str | None) -> bool:
        path = self.resolve_local_path(storage_key)
        if path is None:
            return False

        try:
            path.unlink()
        except OSError:
            return False
        return True
