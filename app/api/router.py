from fastapi import APIRouter

from app.api.routes import analytics, auth, brand, brand_assets, chat, content, folder, jobs, knowledge, render, review, social, storage, template, tenant


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenant.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(brand.router, prefix="/brands", tags=["brands"])
api_router.include_router(brand_assets.router, prefix="/brands", tags=["brand-assets"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(content.router, prefix="/content", tags=["content"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(folder.router, prefix="/folders", tags=["folders"])
api_router.include_router(template.router, prefix="/templates", tags=["templates"])
api_router.include_router(render.router, prefix="/render", tags=["render"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(social.router, prefix="/social", tags=["social"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])
