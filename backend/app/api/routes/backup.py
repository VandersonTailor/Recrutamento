from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import RequireApiKey, require_roles
from app.services.audit import AuditService
from app.services.backup import BackupService


router = APIRouter()


@router.post("/run", dependencies=[RequireApiKey])
def run_backup(
    request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("admin")),
):
    result = BackupService(db).run()
    AuditService(db).log(action="backup.run", ip=request.client.host if request.client else None, metadata=result)
    return result
