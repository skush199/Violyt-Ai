# Frontend Setup

## Scope

The frontend workspace now lives in [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend). It is a Next.js app-router codebase that was imported from the existing partial UI bundle and kept separate from the backend Python package.

The frontend workspace is now connected to the FastAPI backend contracts for auth, tenant admin, brand spaces, content/chat flows, sharing/review, analytics, and user management. Mock mode is still available for UI-only review.

## Important Paths

- Frontend root: [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend)
- Frontend package file: [frontend/package.json](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\package.json)
- Frontend env template: [frontend/.env.example](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\.env.example)
- API client helper: [frontend/lib/api/client.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\lib\api\client.ts)
- API endpoint map: [frontend/lib/api/endpoints.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\lib\api\endpoints.ts)

## Local Setup

1. Install Node.js 20+ and npm.
2. Open a terminal in [frontend](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend).
3. Copy `.env.example` to `.env.local`.
4. Install dependencies.
5. Start the dev server.

Example:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

## Docker Setup

If the team wants to avoid local Node version issues, use the repo Docker flow instead.

From the repo root:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

That starts:

- PostgreSQL
- backend API
- worker
- frontend on Node 20

See [DOCKER_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DOCKER_SETUP.md) for the full steps.

## Expected Local URLs

- Frontend dev server: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Backend docs: `http://localhost:8000/docs`

## Current Env Variables

- `NEXT_PUBLIC_ENV`
- `NEXT_PUBLIC_API_BASE_URI`
- `NEXT_PUBLIC_ENABLE_MOCK_UI`
- `NEXT_PUBLIC_MOCK_ROLE`

For the current integrated UI, `NEXT_PUBLIC_API_BASE_URI` should point to the backend origin, not the `/api/v1` path. The frontend endpoint map already includes `/api/v1`.

Suggested local values:

```env
NEXT_PUBLIC_ENV=development
NEXT_PUBLIC_API_BASE_URI=http://localhost:8000
NEXT_PUBLIC_ENABLE_MOCK_UI=true
NEXT_PUBLIC_MOCK_ROLE=TENANT_ADMIN
```

## Current Notes

- Mock UI mode is enabled by default so the team can review screens without waiting for backend availability.
- Supported preview roles in mock mode: `TENANT_ADMIN`, `TENANT_USER`, `BRAND_USER`, `PLATFORM_OWNER`.
- The main UI routes are wired to the current FastAPI backend contracts.
- Frontend lint passes locally.
- Frontend production build requires Node `>=20.9.0`, which is already handled by the Docker frontend image.

## Key Preview Routes

- `/auth/login`
- `/auth/activate`
- `/dashboard`
- `/brand_space`
- `/brand_space/new`
- `/brand_space/jiraaf`
- `/brand_space/jiraaf/sharing`
- `/user_management`
- `/user_management/create`
- `/user_management/brand-user-a`
- `/profile`

## Immediate Next Step

After design consolidation, the next phase is:

1. run `npm install` and `npm run build` on a machine with Node.js available
2. verify live auth, brand scope, chat, review, and content flows against the local backend
3. replace any remaining mock-only screen data with live analytics and profile editing behavior
4. add frontend lint/build verification in local and CI flows
