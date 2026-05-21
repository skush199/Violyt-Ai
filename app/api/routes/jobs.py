from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.job import JobResponse
from app.services.jobs import JobService


router = APIRouter()


@router.get("/list", response_model=list[JobResponse])
async def list_jobs(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[JobResponse]:
    jobs = await JobService(session).list_for_tenant(principal.tenant_id)
    return [JobResponse.model_validate(item) for item in jobs]


@router.get("/{job_id}/status", response_model=JobResponse)
async def job_status(
    job_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await JobService(session).get_scoped(job_id, principal.tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)
