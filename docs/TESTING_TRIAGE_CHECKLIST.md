# Testing Triage Checklist

Use this checklist when the product feels broadly broken and the team needs a clear picture of what works, what fails, and where to start fixing.

## Current Local Baseline

Checked on 2026-04-23 from `C:\Users\rkart\Violyt`.

| Area | Result | Notes |
| --- | --- | --- |
| Python syntax compile | PASS | `python -m compileall app tests main.py` completed successfully. |
| Backend pytest collection | BLOCKED | `tests/test_auth_service.py`, `tests/test_security.py`, and `tests/test_tenant_service.py` fail collection because `PyJWT` and `email-validator` are missing in the active Python environment. |
| Backend pytest without collection blockers | PARTIAL | `238 passed`, `21 failed`, `1 error`, `3 warnings` when those three files are ignored. |
| Python virtualenv | BROKEN | `.venv` points to `C:\Users\sudha\AppData\Local\Programs\Python\Python312\python.exe`, which does not exist on this machine. |
| Frontend local dependencies | BLOCKED | `frontend/node_modules` is missing. `pnpm --version` attempted to write under AppData and was blocked in the sandbox. |

Before judging product functionality, fix the environment so everyone is running the same stack.

## Step 1: Environment Sanity

Run these first. If any fail, record the issue as setup/environment, not product behavior.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m compileall app tests main.py
```

Expected:

- Python should be 3.12.x if possible because the docs and project target Python 3.12.
- `pip install -e ".[dev]"` should install `PyJWT`, `email-validator`, `pytest`, and other required backend dependencies.
- Compile should pass before deeper testing starts.

For frontend:

```powershell
cd frontend
corepack enable
pnpm install
pnpm lint
pnpm build
```

Expected:

- Dependencies install cleanly.
- Lint passes.
- Production build passes.

If local Node or pnpm causes machine-specific issues, use Docker for the team baseline instead.

## Step 2: Backend Automated Tests

Run the full backend suite:

```powershell
python -m pytest
```

Record results in this format:

| Test command | Pass | Fail | Error | Blocker summary |
| --- | ---: | ---: | ---: | --- |
| `python -m pytest` |  |  |  |  |

Current known failure groups from the partial run:

| Group | What it means |
| --- | --- |
| Layout decision and template recommendation | Template selection/reranking behavior is not matching expected decisions. |
| AI orchestrator prompt rules | Final render and carousel prompt safety/copy rules changed or regressed. |
| Brand asset analysis | Logo/visual region/font extraction tests are failing. |
| Content generation/export helpers | Generation context and export behavior have failing edge cases. |
| Template service | Some template metadata defaults and doc analysis paths are failing. |
| Data visualization parser | Chart parsing from prompt/metadata is failing. |
| Temporary directory permission | One image provider test cannot create pytest temp files under AppData on this machine. |

## Step 3: Docker Integration Smoke

Use Docker as the shared team truth because it avoids local Python/Node drift.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

After services are healthy, load sample data:

```powershell
Get-Content docs\sample_db_seed.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U violyt -d violyt
```

Then run the live API smoke test:

```powershell
python scripts/live_smoke_api.py
```

This smoke test checks:

- Activate sample user.
- Login.
- Auth `/me`.
- Brand overview.
- Template recommendation.
- Content generation.
- Render preview.
- Content export.
- Review share link.
- Review page and comment.
- Chat session and message.
- Brand analytics.
- Jobs list.

Record it like this:

| Smoke step | Status | HTTP status | Notes or error |
| --- | --- | ---: | --- |
| activate_sample_user |  |  |  |
| login |  |  |  |
| auth_me |  |  |  |
| brand_overview |  |  |  |
| template_recommend |  |  |  |
| content_generate |  |  |  |
| render_preview |  |  |  |
| content_export |  |  |  |
| review_share_link |  |  |  |
| review_get |  |  |  |
| review_comment |  |  |  |
| chat_create_session |  |  |  |
| chat_send_message |  |  |  |
| brand_analytics |  |  |  |
| jobs_list |  |  |  |

## Step 4: Manual Product Flow Matrix

Have one tester run these from the frontend and one tester verify the related API response in Swagger or browser dev tools.

| Feature | Manual test | Expected result | Status | Evidence |
| --- | --- | --- | --- | --- |
| Frontend boot | Open `http://localhost:3000` | App loads without console/network errors. |  |  |
| Auth | Activate sample user, then login | User reaches workspace/dashboard. |  |  |
| Brand Space | Open sample Brand Space overview | Brand identity, guardrails, and visual identity load. |  |  |
| Knowledge upload | Upload a small PDF/image/logo | Upload succeeds and a processing job is created. |  |  |
| Worker processing | Wait for worker, check jobs | Job completes and extracted knowledge appears. |  |  |
| Template recommendation | Ask for an Instagram or LinkedIn creative | Relevant templates are returned with signed asset URLs. |  |  |
| Content generation | Generate one static PNG creative | Content version is created and has usable generated payload. |  |  |
| Image generation | Generate with image enabled | AI or mock image asset appears, depending on provider config. |  |  |
| Preview render | Click/render preview | Preview image opens and matches selected format size. |  |  |
| Export | Export PNG/PDF | Downloadable/export asset is created. |  |  |
| Chat | Send follow-up message | Assistant responds and references prior context correctly. |  |  |
| Review link | Create review link | Public review page opens without auth. |  |  |
| Review comment | Add external comment | Comment is saved and visible. |  |  |
| Analytics | Open analytics | Brand/platform analytics load without 500s. |  |  |
| Role/RBAC | Login as different role if available | User only sees allowed actions/data. |  |  |

## Step 5: Bug Report Format

Every failed item should be logged with enough detail for a developer to reproduce it.

```text
Feature:
Environment: local / Docker / staging
Command or URL:
Input used:
Expected:
Actual:
HTTP status / traceback:
Screenshot or generated asset path:
Repro steps:
Severity: blocker / high / medium / low
Owner:
```

## What To Tell The Team

Use three labels only:

- Working: repeatable pass in Docker or a clean local environment.
- Broken: repeatable fail with clear expected vs actual behavior.
- Blocked: cannot test because setup, dependency, seed data, provider key, database, or permissions are missing.

Do not mix these labels. A missing dependency is not the same as a failed product feature.
