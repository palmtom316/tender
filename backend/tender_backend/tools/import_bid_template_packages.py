from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg

from tender_backend.services.template_service.package_importer import (
    import_template_package_from_directory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import bid template package directories into the database.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-root", required=True, help="Directory containing one or more template package folders.")
    args = parser.parse_args()

    root = Path(args.source_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"source root is not a directory: {root}")

    imported: list[dict[str, object]] = []
    with psycopg.connect(args.database_url) as conn:
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            result = import_template_package_from_directory(conn, source_dir=child)
            imported.append({
                "package_id": result.package_id,
                "package_key": result.package_key,
                "display_name": result.display_name,
                "package_type": result.package_type,
                "item_count": result.item_count,
            })

    print(json.dumps({"imported": imported}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
