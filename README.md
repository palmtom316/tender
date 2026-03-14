# Tender

AI-assisted tender document authoring system for technical bids.

## Workspace

- `backend/`: FastAPI business API
- `ai_gateway/`: model routing and credential proxy
- `frontend/`: React + Vite internal console
- `infra/`: local Docker Compose and OpenSearch config
- `docs/`: PRD, plans, and tracking artifacts

## Quick Start

1. Copy `infra/.env.example` to `infra/.env` and adjust secrets if needed.
2. Start infrastructure only:
   - `docker compose --env-file infra/.env -f infra/docker-compose.yml up -d postgres redis minio opensearch`
3. Run backend locally:
   - `cd backend && ../.venv/bin/uvicorn tender_backend.main:app --reload`
4. Run AI gateway locally:
   - `cd ai_gateway && ../.venv/bin/uvicorn tender_ai_gateway.main:app --reload --port 8100`
5. Run frontend locally:
   - `cd frontend && npm run dev`

## Verification

- Backend tests: `cd backend && ../.venv/bin/pytest`
- AI gateway tests: `cd ai_gateway && ../.venv/bin/pytest`
- Frontend build: `cd frontend && npm run build`
- Compose config: `docker compose --env-file infra/.env -f infra/docker-compose.yml config`
