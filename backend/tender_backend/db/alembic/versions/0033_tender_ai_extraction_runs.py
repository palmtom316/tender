"""tender ai extraction runs

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-03
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tender_ai_extraction_run (
          id UUID PRIMARY KEY,
          tender_document_id UUID NOT NULL REFERENCES tender_document(id) ON DELETE CASCADE,
          project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
          status TEXT NOT NULL DEFAULT 'pending',
          mode TEXT NOT NULL DEFAULT 'requirements',
          model_policy TEXT NOT NULL DEFAULT 'v4_flash_then_pro',
          total_batches INT NOT NULL DEFAULT 0,
          succeeded_batches INT NOT NULL DEFAULT 0,
          failed_batches INT NOT NULL DEFAULT 0,
          skipped_batches INT NOT NULL DEFAULT 0,
          total_chunks INT NOT NULL DEFAULT 0,
          covered_chunks INT NOT NULL DEFAULT 0,
          extracted_requirements INT NOT NULL DEFAULT 0,
          total_input_tokens INT NOT NULL DEFAULT 0,
          total_output_tokens INT NOT NULL DEFAULT 0,
          error TEXT NULL,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          started_at TIMESTAMPTZ NULL,
          finished_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tender_ai_extraction_batch (
          id UUID PRIMARY KEY,
          run_id UUID NOT NULL REFERENCES tender_ai_extraction_run(id) ON DELETE CASCADE,
          tender_document_id UUID NOT NULL REFERENCES tender_document(id) ON DELETE CASCADE,
          tender_document_file_id UUID NULL REFERENCES tender_document_file(id) ON DELETE SET NULL,
          source_file TEXT NOT NULL,
          batch_index INT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          chunk_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          chunk_count INT NOT NULL DEFAULT 0,
          input_char_count INT NOT NULL DEFAULT 0,
          estimated_input_tokens INT NOT NULL DEFAULT 0,
          model TEXT NOT NULL,
          reasoning_effort TEXT NULL,
          response_format TEXT NOT NULL DEFAULT 'json_object',
          retry_count INT NOT NULL DEFAULT 0,
          max_retries INT NOT NULL DEFAULT 2,
          input_tokens INT NOT NULL DEFAULT 0,
          output_tokens INT NOT NULL DEFAULT 0,
          latency_ms INT NOT NULL DEFAULT 0,
          extracted_requirements INT NOT NULL DEFAULT 0,
          dropped_invalid INT NOT NULL DEFAULT 0,
          error_type TEXT NULL,
          error_message TEXT NULL,
          skip_reason TEXT NULL,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          started_at TIMESTAMPTZ NULL,
          finished_at TIMESTAMPTZ NULL,
          UNIQUE (run_id, source_file, batch_index)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tender_ai_run_document_status "
        "ON tender_ai_extraction_run (tender_document_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tender_ai_batch_run_status "
        "ON tender_ai_extraction_batch (run_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tender_ai_batch_file_status "
        "ON tender_ai_extraction_batch (tender_document_file_id, status);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tender_ai_batch_file_status;")
    op.execute("DROP INDEX IF EXISTS idx_tender_ai_batch_run_status;")
    op.execute("DROP INDEX IF EXISTS idx_tender_ai_run_document_status;")
    op.execute("DROP TABLE IF EXISTS tender_ai_extraction_batch;")
    op.execute("DROP TABLE IF EXISTS tender_ai_extraction_run;")
