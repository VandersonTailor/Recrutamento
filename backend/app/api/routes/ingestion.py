import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import RequireApiKey, current_role, require_roles
from app.schemas.ingestion import IngestionJobCreate, IngestionJobOut, IngestionQueueStatsOut, IngestionReport, IngestionScanRequest, IngestionScanResult
from app.services.audit import AuditService
from app.services.ingestion import IngestionService
from app.services.ingestion_queue import IngestionQueueService


router = APIRouter()
SCAN_LOCK = threading.Lock()


@router.post("/scan", response_model=IngestionScanResult)
def scan(
    request: IngestionScanRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    if not SCAN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Já existe uma ingestão síncrona em execução. Use /scan/queue.")
    service = IngestionService(db)
    try:
        result = service.scan_recv_dir(job_id=request.job_id, force_reanalyze=request.force_reanalyze)
        AuditService(db).log(action="ingestion.scan", ip=http_request.client.host if http_request.client else None, metadata=result)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        SCAN_LOCK.release()


@router.post("/report", dependencies=[RequireApiKey])
def report(
    payload: IngestionReport,
    http_request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    service = IngestionService(db)
    result = service.ingest_report_from_bot(payload.model_dump())
    AuditService(db).log(action="ingestion.report", ip=http_request.client.host if http_request.client else None, metadata=result)
    return result


@router.post("/reconcile")
def reconcile(
    http_request: Request,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    service = IngestionService(db)
    result = service.reconcile_candidates_from_resumes()
    AuditService(db).log(action="ingestion.reconcile", ip=http_request.client.host if http_request.client else None, metadata=result)
    return result


@router.post("/scan/queue", response_model=IngestionJobOut)
def enqueue_scan(
    payload: IngestionJobCreate,
    http_request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(current_role),
    _authorized: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    service = IngestionQueueService(db)
    row = service.enqueue(
        requested_by=role,
        requested_ip=http_request.client.host if http_request.client else None,
        job_id=payload.job_id,
        force_reanalyze=payload.force_reanalyze,
    )
    AuditService(db).log(
        action="ingestion.scan.queue",
        ip=http_request.client.host if http_request.client else None,
        metadata={"ingestion_job_id": row.id, "job_id": payload.job_id, "force_reanalyze": payload.force_reanalyze},
        actor=role,
    )
    return row


@router.get("/scan/queue", response_model=list[IngestionJobOut])
def list_scan_queue(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    return IngestionQueueService(db).list_jobs(status=status, limit=limit)


@router.get("/scan/queue/stats", response_model=IngestionQueueStatsOut)
def queue_stats(
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("manager", "admin")),
):
    return IngestionQueueService(db).stats()


@router.get("/scan/queue/{ingestion_job_id}", response_model=IngestionJobOut)
def get_scan_queue_job(
    ingestion_job_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    row = IngestionQueueService(db).get_job(ingestion_job_id=ingestion_job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job de ingestão não encontrado.")
    return row
