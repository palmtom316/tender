from __future__ import annotations

import os
from pathlib import Path


class ProjectFileStorage:
    """Resolve and manage project_file storage keys.

    Today the codebase stores two shapes of keys:
    - local absolute paths for standard PDFs uploaded into the local standards volume
    - object-storage style keys such as `tender-raw/...` for generic project files

    Centralizing this check keeps API/workflow code from hard-coding filesystem
    assumptions, while still supporting the current local-standard-PDF flow.
    """

    @staticmethod
    def _normalized_filename_key(filename: str | None) -> str:
        return "".join(str(filename or "").split()).casefold()

    def _fallback_search_dirs(self) -> list[Path]:
        repo_root = Path(__file__).resolve().parents[4]
        configured_dirs = [
            value.strip()
            for value in os.environ.get("STANDARD_PDF_FALLBACK_DIRS", "").split(os.pathsep)
            if value.strip()
        ]
        candidate_dirs = [
            *(Path(value) for value in configured_dirs),
            repo_root / "docs" / "OCR",
            repo_root / "data" / "standards",
            repo_root / "backend" / "data" / "standards",
        ]
        existing_dirs: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidate_dirs:
            resolved = candidate.resolve()
            if resolved in seen or not resolved.is_dir():
                continue
            seen.add(resolved)
            existing_dirs.append(resolved)
        return existing_dirs

    def _resolve_by_filename(self, filename: str | None) -> Path | None:
        normalized_name = Path(str(filename or "").strip()).name
        if not normalized_name:
            return None
        normalized_key = self._normalized_filename_key(normalized_name)
        for directory in self._fallback_search_dirs():
            candidate = directory / normalized_name
            if candidate.is_file():
                return candidate
            for sibling in directory.iterdir():
                if not sibling.is_file():
                    continue
                if self._normalized_filename_key(sibling.name) == normalized_key:
                    return sibling
        return None

    def resolve_local_path(self, storage_key: str | None, *, filename: str | None = None) -> Path | None:
        if not storage_key:
            return self._resolve_by_filename(filename)

        candidate = Path(storage_key)
        if candidate.is_absolute() and candidate.is_file():
            return candidate
        return self._resolve_by_filename(filename)

    def delete_managed_file(self, storage_key: str | None) -> bool:
        path = self.resolve_local_path(storage_key)
        if path is None:
            return False

        try:
            path.unlink()
        except OSError:
            return False
        return True
