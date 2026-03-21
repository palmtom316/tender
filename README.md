# Tender

AI-assisted tender document authoring system for technical bids.

## Workspace

- `backend/`: FastAPI business API
- `ai_gateway/`: model routing and credential proxy
- `frontend/`: React + Vite internal console
- `infra/`: local Docker Compose and OpenSearch config
- `docs/`: PRD, plans, and tracking artifacts

## Quick Start

1. Create the shared Python virtualenv and install editable backend/gateway deps:
   - `python3 -m venv .venv`
   - `.venv/bin/pip install -e 'backend[dev]' -e 'ai_gateway[dev]'`
2. Copy `infra/.env.example` to `infra/.env` and adjust secrets if needed.
   - `tag_clauses` defaults to SiliconFlow primary (`deepseek-ai/DeepSeek-V3.2`) and Qwen fallback in code/migrations.
   - Keep `DEEPSEEK_API_KEY` and `SILICONFLOW_API_KEY` only in your private `infra/.env`, never in git.
3. Start infrastructure only:
   - `docker compose --env-file infra/.env -f infra/docker-compose.yml up -d postgres redis minio opensearch`
4. Run backend locally:
   - `cd backend && ../.venv/bin/uvicorn tender_backend.main:app --reload`
5. Run AI gateway locally:
   - `cd ai_gateway && ../.venv/bin/uvicorn tender_ai_gateway.main:app --reload --port 8100`
6. Run frontend locally:
   - `cd frontend && npm run dev`

## Verification

- Backend tests: `cd backend && ../.venv/bin/pytest`
- Backend integration tests (example): `cd backend && DATABASE_URL=postgresql://tender:change-me@localhost:5432/tender ../.venv/bin/pytest tests/integration/test_standard_viewer_query_api.py -q`
- Reindex all standard clauses: `cd backend && ../.venv/bin/python -m tender_backend.tools.reindex_standard_clauses --all`
- AI gateway tests: `cd ai_gateway && ../.venv/bin/pytest`
- Frontend build: `cd frontend && npm run build`
- Compose config: `docker compose --env-file infra/.env -f infra/docker-compose.yml config`
