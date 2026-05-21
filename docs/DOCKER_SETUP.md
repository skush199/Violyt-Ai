# Docker Setup

This repo now ships with a full local Docker flow for:

- FastAPI backend API
- background worker
- PostgreSQL
- Next.js frontend

## What Docker Starts

`docker-compose.yml` now includes:

- `postgres`
- `api`
- `worker`
- `frontend`

The backend and worker share the same image and mounted storage paths. The frontend uses a Node 20 image so the team does not hit the local Node 18 / Next 16 version mismatch.

## Prerequisites

1. Install Docker Desktop.
2. Make sure Docker Desktop is running.
3. Copy `.env.example` to `.env` in the repo root.

Example:

```powershell
Copy-Item .env.example .env
```

## Recommended Local `.env`

At minimum, set:

```env
SECRET_KEY=change-this-secret
SOCIAL_ENCRYPTION_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
```

Notes:

- Docker Compose automatically overrides the database host to `postgres` for the backend and worker containers.
- `GENERATED_ASSETS_BASE_URL` should remain `http://localhost:8000/storage` for local use so the frontend can open backend-rendered assets from the browser.

## Start The Full Stack

From the repo root:

```powershell
docker compose up --build
```

This will:

1. start PostgreSQL
2. build the shared backend image
3. run Alembic migrations before starting the API
4. start the worker using the same backend image
5. build the frontend with Node 20
6. expose the frontend and backend locally

## Local URLs

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Backend Swagger: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

## Optional Sample Data

After the stack is up, load the sample seed:

```powershell
Get-Content docs\sample_db_seed.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U violyt -d violyt
```

Then use:

- platform owner activation token: `sample-activation-token-owner`
- platform owner email: `owner@violyt.ai`
- platform owner password to set: `DemoPass123!`
- activation token: `sample-activation-token-admin`
- email: `admin@sampletenant.com`
- password to set: `DemoPass123!`

## Stop The Stack

```powershell
docker compose down
```

To also remove the persisted database volume:

```powershell
docker compose down -v
```

## Rebuild After Code Changes

If you change backend or frontend dependencies, rebuild:

```powershell
docker compose up --build
```

If you want a fully clean rebuild:

```powershell
docker compose build --no-cache
docker compose up
```

If Docker has intermittent internet or DNS issues, avoid repeated `--no-cache` rebuilds because that forces all Python wheels to download again. Once the first build succeeds, prefer:

```powershell
docker compose up --build
```

## Common Notes

- The frontend is built with `NEXT_PUBLIC_API_BASE_URI=http://localhost:8000` so browser requests work from the host machine.
- The worker uses the same storage and vector-store paths as the backend.
- The worker reuses the same backend Docker image as the API service.
- Rendered assets are written into the repo-local [storage](C:\Users\sudha\OneDrive\Desktop\Violyt\storage) folder and served from `http://localhost:8000/storage/...`.
- Vector indexes are written into the repo-local [vector_store](C:\Users\sudha\OneDrive\Desktop\Violyt\vector_store) folder.
- If you do not set provider keys, generation can still run with fallback behavior, but output quality will be lower.

## Suggested Team Smoke Flow

1. Start the full stack with Docker.
2. Load `sample_db_seed.sql`.
3. Open Swagger at `http://localhost:8000/docs`.
4. Activate and login with the sample user.
5. Open the frontend at `http://localhost:3000`.
6. Create or review Brand Space data.
7. Generate content and render output.
8. Test chat, review links, and comments.
