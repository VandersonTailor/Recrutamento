from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.applications import router as applications_router
from app.api.routes.candidates import router as candidates_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.resumes import router as resumes_router
from app.api.routes.search import router as search_router
from app.api.routes.templates import router as templates_router
from app.api.routes.backup import router as backup_router
from app.api.routes.consents import router as consents_router
from app.api.routes.audit import router as audit_router
from app.api.routes.communications import router as communications_router
from app.api.routes.ai_quality import router as ai_quality_router
from app.api.routes.automation_rules import router as automation_rules_router
from app.api.routes.departments import router as departments_router
from app.api.routes.ops import router as ops_router
from app.api.routes.processing_logs import router as processing_logs_router
from app.core.security import RequireApiOrToken

api_router = APIRouter(prefix="/api/v1")
protected_router = APIRouter(dependencies=[RequireApiOrToken])

@api_router.get("")
def root():
    return {"status": "ok"}

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])

protected_router.include_router(ingestion_router, prefix="/ingestion", tags=["ingestion"])
protected_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
protected_router.include_router(candidates_router, prefix="/candidates", tags=["candidates"])
protected_router.include_router(applications_router, prefix="/applications", tags=["applications"])
protected_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
protected_router.include_router(search_router, prefix="/search", tags=["search"])
protected_router.include_router(templates_router, prefix="/templates", tags=["templates"])
protected_router.include_router(resumes_router, prefix="/resumes", tags=["resumes"])
protected_router.include_router(backup_router, prefix="/backup", tags=["backup"])
protected_router.include_router(audit_router, prefix="/audit", tags=["audit"])
protected_router.include_router(communications_router, prefix="/communications", tags=["communications"])
protected_router.include_router(consents_router, prefix="/consents", tags=["consents"])
protected_router.include_router(ai_quality_router, prefix="/ai-quality", tags=["ai-quality"])
protected_router.include_router(automation_rules_router, prefix="/automation-rules", tags=["automation-rules"])
protected_router.include_router(ops_router, prefix="/ops", tags=["ops"])
protected_router.include_router(departments_router, prefix="/departments", tags=["departments"])
protected_router.include_router(processing_logs_router, prefix="/processing_logs", tags=["processing"])

api_router.include_router(protected_router)
