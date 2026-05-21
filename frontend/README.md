# Violyt Frontend

This folder contains the imported partial Next.js frontend workspace for Violyt / BrandLoveStudio.AI.

## Status

- UI workspace added to the repo
- kept separate from the backend Python package
- live backend integration is now wired for auth, tenants, brand spaces, chat, content generation, review, analytics, and user management
- mock mode is still available for design review or partial backend bring-up

## Local Setup

1. Install Node.js 20+ and npm.
2. Copy `.env.example` to `.env.local`.
3. Install dependencies.
4. Start the app.

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

## Docker Setup

If you want a team-friendly local startup without managing Node locally, use the repo Docker stack from the project root:

```powershell
Copy-Item ..\\.env.example ..\\.env
cd ..
docker compose up --build
```

That starts:

- frontend on `http://localhost:3000`
- backend on `http://localhost:8000`
- Swagger on `http://localhost:8000/docs`

Full details: [docs/DOCKER_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\DOCKER_SETUP.md)

## Modes

The frontend can run in either:

- live API mode against the FastAPI backend
- mock UI mode for design-only review

Use `frontend/.env.example` as the base and switch roles with:

```env
NEXT_PUBLIC_ENABLE_MOCK_UI=true
NEXT_PUBLIC_MOCK_ROLE=TENANT_ADMIN
```

To use the live backend instead, set:

```env
NEXT_PUBLIC_API_BASE_URI=http://localhost:8000
NEXT_PUBLIC_ENABLE_MOCK_UI=false
```

Supported mock roles:

- `TENANT_ADMIN`
- `TENANT_USER`
- `BRAND_USER`
- `PLATFORM_OWNER`

## Key Files

- App router: [app](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\app)
- Components: [components](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\components)
- API client: [lib/api/client.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\lib\api\client.ts)
- Endpoint map: [lib/api/endpoints.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\lib\api\endpoints.ts)
- Content/chat hooks: [hooks/useContentWorkspace.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\hooks\useContentWorkspace.ts)
- Tenant hooks: [hooks/tenantAdmins/useGetTenants.ts](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\hooks\tenantAdmins\useGetTenants.ts)
- Env template: [frontend/.env.example](C:\Users\sudha\OneDrive\Desktop\Violyt\frontend\.env.example)

More detail: [docs/FRONTEND_SETUP.md](C:\Users\sudha\OneDrive\Desktop\Violyt\docs\FRONTEND_SETUP.md)
