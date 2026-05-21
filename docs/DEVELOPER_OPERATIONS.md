# Developer Operations

## Runtime Summary

- Language: Python 3.12
- Web framework: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy async
- Migrations: Alembic
- AI providers: OpenAI and Anthropic, selected through config
- OCR: Google Vision wrapper plus document fallbacks
- Vector store: FAISS provider with hash-embedding fallback when OpenAI embeddings are unavailable
- Object storage: local filesystem provider

## Important Paths

- API entrypoint: `main.py`
- Settings: `app/core/config.py`
- Environment template: `.env.example`
- Frontend root: `frontend`
- Frontend env template: `frontend/.env.example`
- Docker compose: `docker-compose.yml`
- Worker entrypoint: `scripts/run_worker.py`
- Alembic config: `alembic.ini`
- Storage directory: `./storage`
- Vector store directory: `./vector_store`

## Environment Setup

1. Create a virtual environment.
2. Install the package and development tools.
3. Copy `.env.example` to `.env`.
4. Update database and provider keys.

Example:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env
```

## Frontend Setup

The repo now includes a separate Next.js frontend workspace under `frontend`.

Example:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

See `docs/FRONTEND_SETUP.md` for the frontend-specific notes and current integration status.

## Minimum `.env` You Should Configure

- `SECRET_KEY`
- `SOCIAL_ENCRYPTION_KEY` if you want a dedicated key for encrypted social tokens. If omitted, the app derives one from `SECRET_KEY`.
- `DATABASE_URL`
- `ALEMBIC_DATABASE_URL`
- `OPENAI_API_KEY` if using OpenAI text, embeddings, or image generation
- `ANTHROPIC_API_KEY` if using Anthropic research or text generation
- `GOOGLE_APPLICATION_CREDENTIALS` if using Google Vision OCR

## Provider Selection

Provider routing is controlled from `.env`.

- `RESEARCH_PROVIDER=anthropic`
- `TEXT_PROVIDER=openai`
- `IMAGE_PROVIDER=openai`
- `FALLBACK_TEXT_PROVIDER=openai`
- `FALLBACK_IMAGE_PROVIDER=mock`

If no OpenAI embedding key is available, the FAISS layer falls back to deterministic hash embeddings for development.

## Database Setup

Start PostgreSQL locally or with Docker compose, then run migrations.

```powershell
docker compose up -d postgres
alembic upgrade head
```

## RBAC Bootstrap

RBAC seed logic runs during FastAPI lifespan startup through `app/services/bootstrap.py`.

To make sure roles and permissions exist, start the API once after the database is migrated.

## Running the API Locally

```powershell
uvicorn main:app --reload
```

Default app URL:

- `http://localhost:8000`

OpenAPI docs:

- `http://localhost:8000/docs`

Static generated assets are mounted at:

- `http://localhost:8000/storage/...`

## Running the Worker

The worker loop polls queued jobs and currently handles:

- knowledge processing
- template analysis

Start it with:

```powershell
python scripts/run_worker.py
```

Worker tuning comes from:

- `WORKER_POLL_INTERVAL_SECONDS`
- `WORKER_BATCH_SIZE`

## Docker Usage

Bring up the full stack:

```powershell
docker compose up --build
```

This uses:

- `Dockerfile` for the FastAPI image
- `frontend/Dockerfile` for the Next.js image
- `docker-compose.yml` for PostgreSQL, API, worker, and frontend

Local URLs:

- `http://localhost:3000` for the frontend
- `http://localhost:8000` for the backend API
- `http://localhost:8000/docs` for Swagger

The current compose flow also:

- runs Alembic migrations before API startup
- starts the worker automatically
- uses a Node 20 image for the frontend

See `docs/DOCKER_SETUP.md` for the team-friendly step-by-step flow including sample data loading.

## Testing

Current focused tests cover:

- blueprint generation
- guardrail validation
- tone evaluation
- provider routing
- chat service logic
- renderer pagination and helper behavior
- content helper merging and blueprint resolution
- password hashing/verification safety for long secrets

Run tests with:

```powershell
python -m pytest
```

Run the live API smoke suite against the seeded sample tenant and local DB with:

```powershell
python scripts/live_smoke_api.py
```

Useful environment overrides:

- `SMOKE_BASE_URL`
- `SMOKE_DB_URL`
- `SMOKE_START_SERVER`
- `SMOKE_EMAIL`
- `SMOKE_PASSWORD`
- `SMOKE_ACTIVATION_TOKEN`
- `SMOKE_BRAND_SPACE_ID`
- `SMOKE_PERSONA_ID`
- `SMOKE_OBJECTIVE_ID`

Lint with:

```powershell
ruff check .
```

## Suggested Local Smoke Test Flow

1. Start PostgreSQL.
2. Run `alembic upgrade head`.
3. Start the API.
4. Authenticate and obtain a bearer token.
5. Create a tenant.
6. Create a Brand Space.
7. Finalize and activate the Brand Space.
8. Upload knowledge.
9. Run the worker to process queued knowledge jobs.
10. Generate content.
11. Render or export output, optionally with blueprint/template overrides.
12. Create a review link and test comments.
13. For admin flows, verify `/api/v1/tenants`, `/api/v1/tenants/{tenant_id}`, `/api/v1/tenants/{tenant_id}/usage-summary`, and `/api/v1/analytics/platform`.

## Deployment Notes

### Application Layer

- Run the API behind a reverse proxy or managed ingress.
- Store secrets in a secret manager, not in source control.
- Mount persistent storage for `storage` and `vector_store` if using local providers.
- Use separate worker processes for background jobs.

### Database Layer

- Use managed PostgreSQL in production.
- Run Alembic migrations during deployment before shifting traffic.
- Back up PostgreSQL and storage paths together if you want full content reconstruction.

### AI Provider Layer

- Set provider keys per environment.
- Keep production defaults in config, not hardcoded in service logic.
- Watch usage limits because content generation, image generation, and OCR are enforced at tenant scope.

### Scaling Notes

- The current object storage and vector store adapters are interface-oriented and can be swapped later.
- `LocalObjectStorage` can be replaced with S3-compatible storage.
- `FaissVectorStoreProvider` can be replaced with PGVector or another remote vector backend.
- The worker loop can be replaced with Celery, RQ, Dramatiq, or another queue without changing route contracts.

## Troubleshooting

### API starts but auth fails

- Check `SECRET_KEY`.
- Make sure the tenant user is activated.
- Make sure the bearer token is passed in `Authorization: Bearer <token>`.

### Knowledge uploads succeed but retrieval is empty

- Confirm the worker is running.
- Check the `jobs` table or `/api/v1/jobs` endpoints.
- Confirm OCR extracted text and the vector store path is writable.

### Images are not generated

- Check `IMAGE_PROVIDER`.
- If OpenAI image generation is not configured, the mock image provider may be used as fallback.

### Anthropic is not being used

- Check `RESEARCH_PROVIDER` or `TEXT_PROVIDER`.
- Make sure `ANTHROPIC_API_KEY` is set.

### Render output looks basic

- Rendering is backend-owned and deterministic, but now respects blueprint overrides, template zone maps, logo placement, and Studio Panel sizing more closely.
- Carousel/PDF/infographic flows can export multiple pages/assets; check `renderer_metadata.page_count` and `export_assets`.

### Frontend needs template or social state

- Use `/api/v1/templates/recommend` before generation when you want prompt-aware template matching.
- Use `/api/v1/social/list` to hydrate the social connection state for the selected Brand Space.

## Recommended Next Hardening Steps

- Add CI for lint, tests, and migration checks.
- Add dedicated worker deployment.
- Add production object storage and vector store providers.
- Add Redis or queue middleware for job dispatch.
- Add structured logging and tracing.
- Add health-check endpoints and readiness probes.
