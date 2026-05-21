# Violyt / BrandLoveStudio.AI

Production-oriented backend, AI orchestration, and frontend workspace for the Violyt / BrandLoveStudio.AI multi-tenant SaaS platform.

## What This Repo Contains

- FastAPI backend APIs
- PostgreSQL data model and Alembic migrations
- multi-tenant auth and RBAC
- Brand Space lifecycle and configuration services
- knowledge upload, OCR, indexing, and retrieval
- multi-model AI orchestration
- deterministic backend rendering
- template analysis and recommendation
- super-admin tenant visibility and platform analytics
- tenant-logo uploads and tenant metadata-backed workspace settings
- chat workspace, history, review, analytics, jobs, and worker scaffolding
- Next.js frontend workspace in [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend)

## Repo Layout

- Backend app: [app](C:\Users\sudha\OneDrive\Desktop\Violyt\app)
- Frontend app: [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend)
- API contracts: [contracts/frontend-api.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\contracts\frontend-api.ts)
- Docs: [docs](C:\Users\sudha\OneDrive\Desktop\Violyt\docs)
- Workers and smoke scripts: [scripts](C:\Users\sudha\OneDrive\Desktop\Violyt\scripts)

## Backend Quick Start

1. Create a virtual environment and install dependencies.
2. Copy `.env.example` to `.env`.
3. Start PostgreSQL.
4. Run `alembic upgrade head`.
5. Start the API once to seed RBAC.
6. Start the worker.
7. Open `http://localhost:8000/docs`.
8. Run `python scripts/live_smoke_api.py` for a local runtime smoke check once PostgreSQL/sample data are ready.

## Frontend Quick Start

1. Install Node.js 20+ and npm.
2. Open [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend).
3. Copy `frontend/.env.example` to `frontend/.env.local`.
4. Run `npm install`.
5. Run `npm run dev`.

Frontend-specific setup notes live in [docs/FRONTEND_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\FRONTEND_SETUP.md).
The frontend now supports both live backend mode and mock UI mode for design review.

Detailed setup and run instructions live in [docs/DEVELOPER_OPERATIONS.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DEVELOPER_OPERATIONS.md).

## Docker Quick Start

The repo now includes a full local Docker stack for:

- PostgreSQL
- FastAPI API
- worker
- Next.js frontend

Quick start:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

The backend Docker image is shared by both the API and worker so the Python dependency layer only has to build once. After the first successful build, prefer `docker compose up --build` over repeated `--no-cache` rebuilds.
Generated preview/export files will be available in the repo-local [storage](C:\Users\sudha\OneDrive\Desktop\Violyt\storage) folder and at `http://localhost:8000/storage/...`.

Then open:

- frontend: `http://localhost:3000`
- backend docs: `http://localhost:8000/docs`

Full Docker instructions live in [docs/DOCKER_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DOCKER_SETUP.md).

## Documentation Index

- [docs/README.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\README.md)
- [docs/ARCHITECTURE.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\ARCHITECTURE.md)
- [docs/API_CONTRACTS.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\API_CONTRACTS.md)
- [docs/CODE_DOCUMENTATION.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\CODE_DOCUMENTATION.md)
- [docs/DB_SCHEMA.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DB_SCHEMA.md)
- [docs/DB_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DB_SETUP.md)
- [docs/DEVELOPER_OPERATIONS.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DEVELOPER_OPERATIONS.md)
- [docs/FRONTEND_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\FRONTEND_SETUP.md)
- [docs/DOCKER_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DOCKER_SETUP.md)

## Frontend Contract

TypeScript request/response contracts are available in [contracts/frontend-api.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\contracts\frontend-api.ts).

## Verification Notes

- The backend codebase is compile-verified with `python -m compileall app tests main.py`.
- The backend regression suite passes locally.
- The frontend lint suite passes locally.
- Frontend production build on this machine is blocked only by the local Node runtime version, which is why the Docker frontend image uses Node 20.
