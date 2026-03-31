from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.services.audit import AuditService
from app.services.ranking import RankingService
from app.models.job import Job


router = APIRouter()


@router.get("")
def list_departments(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    root = settings.recv_dir_path()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"recv_dir não encontrado ou inacessível: {root}")

    items: list[dict] = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        if p.name.startswith("."):
            continue
        items.append({"department": p.name, "path": str(p)})

    items.sort(key=lambda x: x["department"])
    AuditService(db).log(action="departments.list", ip=request.client.host if request.client else None, metadata={"count": len(items)})
    return {"root": str(root), "items": items}


@router.get("/report")
def department_report(department: str, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    root = settings.recv_dir_path()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="recv_dir inválido")
    # Fake job for scoring by department keywords
    job = Job(title=department, department=department, description=f"Departamento {department}", requirements=None, is_active=True)
    ranking = RankingService(db).rank_job(job_id=job.id if getattr(job, "id", None) else 0, department=department, min_score=None, q=None, limit=10, use_cache=False)
    AuditService(db).log(action="departments.report", ip=request.client.host if request.client else None, metadata={"department": department})
    return {"department": department, "top10": ranking.get("items", []), "root": str(root)}
