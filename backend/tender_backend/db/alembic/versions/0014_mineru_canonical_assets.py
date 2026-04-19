"""normalize document.raw_payload to canonical MinerU shape

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-18

Collapses every `document.raw_payload` row to the canonical 4-key dict
`{parser_version, pages, tables, full_markdown}`.

Legacy keys (`batch_id`, `result_item`, etc.) are dropped. `raw_payload->pages`
is preserved only when every entry shape-validates as
`{page_number: int, markdown: string}`; anything else (pipeline-backend
residue, layout-block fragments) is replaced with an empty array so the
next parse can refill it. `raw_payload->tables` is kept as-is when present
(tables are a fresh value, not a reconciliation target), defaulting to
`[]::jsonb`.

Downgrade is a no-op: the old legacy keys were garbage we do not want to
resurrect.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE document
        SET raw_payload = jsonb_build_object(
            'parser_version', COALESCE(raw_payload->>'parser_version', parser_version),
            'pages', CASE
                WHEN jsonb_typeof(raw_payload->'pages') = 'array'
                 AND (
                     SELECT bool_and(
                         jsonb_typeof(p) = 'object'
                         AND (p ? 'page_number')
                         AND (p ? 'markdown')
                         AND jsonb_typeof(p->'page_number') = 'number'
                         AND jsonb_typeof(p->'markdown') = 'string'
                     )
                     FROM jsonb_array_elements(raw_payload->'pages') p
                 ) IS TRUE
                THEN raw_payload->'pages'
                ELSE '[]'::jsonb
            END,
            'tables', COALESCE(raw_payload->'tables', '[]'::jsonb),
            'full_markdown', COALESCE(raw_payload->>'full_markdown', '')
        )
        WHERE raw_payload IS NOT NULL;
        """
    )


def downgrade() -> None:
    # Intentionally a no-op. The pre-0014 shape mixed canonical and provider
    # keys (`batch_id`, `result_item`) that we deliberately dropped; there
    # is nothing useful to restore.
    pass
