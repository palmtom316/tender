-- Initial schema for Tender (v0).
-- Notes:
-- - Avoid extensions in v0 to keep local/dev users simple.
-- - UUIDs are generated in the application layer.

CREATE TABLE IF NOT EXISTS project (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_file (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  storage_key TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document (
  id UUID PRIMARY KEY,
  project_file_id UUID NOT NULL REFERENCES project_file(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS parse_job (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_job_id TEXT NULL,
  error TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_section (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  section_code TEXT NULL,
  title TEXT NOT NULL,
  level INT NOT NULL DEFAULT 1,
  page_start INT NULL,
  page_end INT NULL,
  text TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_table (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
  section_id UUID NULL REFERENCES document_section(id) ON DELETE SET NULL,
  page INT NULL,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_table_override (
  id UUID PRIMARY KEY,
  document_table_id UUID NOT NULL REFERENCES document_table(id) ON DELETE CASCADE,
  override_json JSONB NOT NULL,
  created_by TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_requirement (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  source_text TEXT NULL,
  human_confirmed BOOLEAN NOT NULL DEFAULT false,
  confirmed_by TEXT NULL,
  confirmed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_fact (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  fact_key TEXT NOT NULL,
  fact_value TEXT NOT NULL,
  source_text TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chapter_draft (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  chapter_code TEXT NOT NULL,
  content_md TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS review_issue (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  severity TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT NULL,
  resolved BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS export_record (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  template_name TEXT NULL,
  export_key TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS synonym_dictionary (
  id UUID PRIMARY KEY,
  term TEXT NOT NULL,
  synonyms TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
