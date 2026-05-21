# Violyt Docs

This folder contains the developer-facing Markdown documentation for the current backend, AI services, and frontend workspace.

Repo entrypoint and quick-start summary:

- `README.md`

## Files

- `API_CONTRACTS.md`
  Frontend-to-backend APIs, admin and tenant contracts, internal AI orchestration contracts, renderer contracts, auth rules, payload shapes, and platform/render behaviors.

- `ARCHITECTURE.md`
  Recreated implementation architecture for the current backend, including layers, flows, tenant isolation, AI orchestration, and rendering boundaries.

- `CODE_DOCUMENTATION.md`
  Module-by-module and file-by-file reference for routes, services, AI components, repositories, models, schemas, integrations, workers, and startup wiring.

- `DB_SCHEMA.md`
  PostgreSQL schema reference covering inherited scope columns, tables, relationships, lifecycle fields, and uniqueness rules.

- `DB_SETUP.md`
  PostgreSQL setup, migrations, RBAC seeding, verification steps, and optional sample data loading.

- `DEVELOPER_OPERATIONS.md`
  Local setup, environment variables, migrations, running the API, running the worker, testing, Docker usage, and deployment notes.

- `FRONTEND_SETUP.md`
  Frontend workspace setup, env variables, local run flow, and the current integration status for the imported Next.js UI codebase.

- `DOCKER_SETUP.md`
  Full-stack Docker instructions for PostgreSQL, API, worker, and frontend.

- `sample_db_seed.sql`
  Optional sample tenant, Brand Space, session, content, and review seed for local development.

## Suggested Reading Order

1. Read `ARCHITECTURE.md` for the implementation-level system picture.
2. Read the repo-root `README.md` for quick start and doc index.
3. Read `API_CONTRACTS.md` if you are integrating frontend, backend, AI orchestration, or rendering.
4. Read `DB_SCHEMA.md` and `DB_SETUP.md` if you are working on persistence or environment setup.
5. Read `CODE_DOCUMENTATION.md` if you are maintaining or extending backend modules.
6. Read `FRONTEND_SETUP.md` if you are working on the Next.js app.
7. Read `DOCKER_SETUP.md` if you want the fastest team-wide local stack bring-up.
8. Read `DEVELOPER_OPERATIONS.md` for local run, test, and deployment workflows.

## Additional References

- FastAPI app entrypoint: `main.py`
- Route registration: `app/api/router.py`
- TypeScript-facing contract file: `contracts/frontend-api.ts`
- Internal AI and renderer contracts: `app/ai/contracts.py`
- Initial database migration: `alembic/versions/0001_initial_schema.py`
