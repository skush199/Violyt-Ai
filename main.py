from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AuthorizationError, DomainError, DuplicateResourceError, GenerationFailureError, GuardrailViolationError, LifecycleError, NotFoundError, UploadValidationError, UsageLimitExceededError
from app.db.session import AsyncSessionLocal
from app.services.bootstrap import seed_demo_owner, seed_rbac


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)
        await seed_demo_owner(session)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_v1_prefix)

storage_dir = Path(settings.object_storage_base_path)
storage_dir.mkdir(parents=True, exist_ok=True)


@app.get("/health", include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


@app.exception_handler(NotFoundError)
async def not_found_handler(_, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DuplicateResourceError)
async def duplicate_resource_handler(_, exc: DuplicateResourceError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(GenerationFailureError)
async def generation_failure_handler(_, exc: GenerationFailureError):
    return JSONResponse(
        status_code=400,
        content={
            "detail": exc.reason_summary,
            "failure": exc.to_payload(),
        },
    )


@app.exception_handler(AuthorizationError)
@app.exception_handler(GuardrailViolationError)
@app.exception_handler(LifecycleError)
@app.exception_handler(UploadValidationError)
@app.exception_handler(UsageLimitExceededError)
async def business_error_handler(_, exc: DomainError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
