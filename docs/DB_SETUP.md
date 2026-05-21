# Database Setup

## Purpose

This document explains how to set up PostgreSQL for the Violyt backend, run migrations, verify the schema, and optionally load a sample dataset.

Related files:

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/0001_initial_schema.py`
- `.env.example`
- `docker-compose.yml`
- `docs/sample_db_seed.sql`

## Prerequisites

- Python 3.12
- PostgreSQL 16 or compatible
- project dependencies installed

## 1. Configure Environment

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Minimum DB-related variables:

```env
DATABASE_URL=postgresql+asyncpg://violyt:violyt@localhost:5432/violyt
ALEMBIC_DATABASE_URL=postgresql+psycopg://violyt:violyt@localhost:5432/violyt
```

Why there are two URLs:

- `DATABASE_URL` is used by the async application runtime
- `ALEMBIC_DATABASE_URL` is used by Alembic and synchronous migration execution

## 2. Start PostgreSQL

### Option A: Docker Compose

```powershell
docker compose up -d postgres
```

Default compose credentials:

- database: `violyt`
- user: `violyt`
- password: `violyt`
- port: `5432`

### Option B: Existing PostgreSQL Server

Create the database and a login role yourself, then point `.env` at that server.

Example SQL:

```sql
CREATE ROLE violyt WITH LOGIN PASSWORD 'violyt';
CREATE DATABASE violyt OWNER violyt;
```

## 3. Install Dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## 4. Run the Initial Migration

```powershell
alembic upgrade head
```

Current implementation detail:

- the initial migration calls `Base.metadata.create_all(...)`
- that means the schema is generated directly from the SQLAlchemy models

## 5. Seed Roles and Permissions

RBAC seed logic runs automatically when the API starts.

Start the API once:

```powershell
uvicorn main:app --reload
```

This seeds:

- roles
- permissions
- role-permission mappings

If you prefer, you can also invoke the app startup path in your normal deployment process before onboarding users.

## 6. Verify the Database

Useful verification steps:

```sql
\dt
SELECT code, name FROM roles ORDER BY code;
SELECT code, name FROM permissions ORDER BY code;
```

Expected role codes:

- `super_admin`
- `tenant_admin`
- `tenant_user`
- `brand_user`
- `external_reviewer`

## 7. Optional: Load Sample Data

A representative sample SQL file is included:

- `docs/sample_db_seed.sql`

It creates:

- one tenant
- one tenant admin user
- one Brand Space
- one default persona
- one guardrail set
- one objective
- one active chat/content session
- one generated content history row
- one review link
- one usage-limit row

Important:

- start the API once before loading the sample seed so the `roles` table is already populated
- the sample seed assumes the `tenant_admin` role exists

Load it with:

```powershell
psql -U violyt -d violyt -f docs/sample_db_seed.sql
```

## 8. Local Developer Flow

Recommended order:

1. Start PostgreSQL.
2. Copy `.env.example` to `.env`.
3. Install dependencies.
4. Run `alembic upgrade head`.
5. Start the API once to seed RBAC.
6. Optionally load `docs/sample_db_seed.sql`.
7. Start the API and worker for normal development.

## 9. Resetting the Local Database

If you want a clean local reset and you are using Docker compose:

```powershell
docker compose down -v
docker compose up -d postgres
alembic upgrade head
uvicorn main:app --reload
```

This removes the Docker-managed PostgreSQL volume and recreates the database from scratch.

## 10. Running the Worker After DB Setup

Knowledge processing and template-analysis jobs need the worker loop.

```powershell
python scripts/run_worker.py
```

Without the worker:

- uploaded knowledge will remain queued for processing
- template analysis jobs will remain queued

## 11. Production Notes

- use managed PostgreSQL rather than local Docker storage
- run Alembic migrations before switching application traffic
- back up PostgreSQL together with object storage if you want complete content and asset recovery
- if you move to PGVector later, the transactional schema can remain mostly unchanged while retrieval storage changes underneath

## 12. Troubleshooting

### Alembic cannot connect

Check:

- PostgreSQL is running
- `ALEMBIC_DATABASE_URL` is correct
- firewall or port mapping is open

### App connects but migrations fail

Check:

- correct driver in each URL
- runtime uses `asyncpg`
- Alembic uses `psycopg`

### Roles are missing after migration

Start the API once so `seed_rbac()` runs.

### Sample seed fails on role lookup

Start the API first, then rerun the seed script.
