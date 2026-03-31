import asyncio
import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.services.alerts import collect_active_alerts
from app.services.backup import BackupService
from app.services.communication_dispatcher import CommunicationDispatcherService
from app.services.ingestion import IngestionService
from app.services.ingestion_queue import IngestionQueueService
from app.services.lgpd_retention import run_retention_cycle
from app.services.metrics import OCR_QUEUE_BACKLOG, render_metrics
import app.models  # noqa: F401


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Recrutamento Carris",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz():
        recv_ok = False
        db_ok = False
        try:
            recv_ok = get_settings().recv_dir_path().exists()
        except Exception:
            recv_ok = False
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
        queue_stats = {}
        communication_stats = {}
        alerts = []
        try:
            db = SessionLocal()
            queue_stats = IngestionQueueService(db).stats()
            communication_stats = CommunicationDispatcherService(db).stats()
            alerts = collect_active_alerts(db)
            db.close()
        except Exception:
            queue_stats = {}
            communication_stats = {}
            alerts = []

        ready = recv_ok and db_ok
        payload = {
            "status": "ready" if ready else "degraded",
            "recv_ok": recv_ok,
            "db_ok": db_ok,
            "ingestion_queue": queue_stats,
            "communication_dispatch": communication_stats,
            "alerts_active": len(alerts),
        }
        if ready:
            return payload
        return JSONResponse(status_code=503, content=payload)

    @app.get("/metrics")
    def metrics():
        return PlainTextResponse(render_metrics().decode("utf-8"), media_type="text/plain; version=0.0.4")

    @app.middleware("http")
    async def _structured_request_log(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        t0 = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            elapsed_ms = int((time.time() - t0) * 1000)
            logging.getLogger("uvicorn.access").info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "elapsed_ms": elapsed_ms,
                        "client_ip": request.client.host if request.client else None,
                    },
                    ensure_ascii=False,
                )
            )

    @app.exception_handler(FileNotFoundError)
    def _handle_not_found(_: Request, exc: FileNotFoundError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    def _handle_perm(_: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.on_event("startup")
    async def _startup() -> None:
        Base.metadata.create_all(bind=engine)
        _ensure_schema_upgrade()
        _ensure_recv_dir_accessible()
        _start_backup_scheduler()
        _start_missing_cleanup_scheduler()
        _start_ingestion_queue_worker()
        _start_auto_ingestion_scheduler()
        _start_communication_dispatch_worker()
        _start_alerts_evaluator()
        _start_lgpd_retention_scheduler()

    return app


app = create_app()


def _ensure_recv_dir_accessible() -> None:
    settings = get_settings()
    recv_dir = settings.recv_dir_path()
    try:
        if not recv_dir.exists() or not recv_dir.is_dir():
            logging.getLogger("uvicorn.error").warning(f"recv_dir não encontrado/inacessível: {recv_dir}")
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning(f"recv_dir inacessível por permissão/erro: {recv_dir} ({exc})")


def _start_backup_scheduler() -> None:
    settings = get_settings()
    if not settings.backup_enabled:
        return

    interval = max(5, int(settings.backup_interval_minutes))
    logger = logging.getLogger("uvicorn.error")

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval * 60)
                await asyncio.to_thread(_run_backup_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _run_backup_once(logger: logging.Logger) -> None:
    db = SessionLocal()
    try:
        result = BackupService(db).run()
        logger.info(f"backup: {result}")
    finally:
        db.close()

def _start_missing_cleanup_scheduler() -> None:
    logger = logging.getLogger("uvicorn.error")
    async def _loop():
        while True:
            try:
                await asyncio.sleep(60)
                await asyncio.to_thread(_run_missing_cleanup_once, logger)
            except Exception:
                continue
    asyncio.create_task(_loop())


def _start_ingestion_queue_worker() -> None:
    logger = logging.getLogger("uvicorn.error")
    interval = max(2, int(get_settings().ingestion_queue_poll_seconds))

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(_run_ingestion_queue_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _start_auto_ingestion_scheduler() -> None:
    settings = get_settings()
    if not settings.ingestion_auto_enabled:
        return
    interval = max(15, int(settings.ingestion_auto_interval_minutes or 60))
    logger = logging.getLogger("uvicorn.error")

    async def _loop():
        # Executa uma carga completa na partida para refletir toda a pasta de rede
        try:
            await asyncio.to_thread(_run_auto_ingestion_once, logger)
        except Exception:
            pass
        while True:
            try:
                await asyncio.sleep(interval * 60)
                await asyncio.to_thread(_run_auto_ingestion_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _start_communication_dispatch_worker() -> None:
    settings = get_settings()
    if not settings.communication_dispatch_enabled:
        return

    logger = logging.getLogger("uvicorn.error")
    interval = max(5, int(settings.communication_dispatch_poll_seconds or 20))

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(_run_communication_dispatch_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _run_ingestion_queue_once(logger: logging.Logger) -> None:
    db = SessionLocal()
    try:
        stats = IngestionQueueService(db).stats()
        pending = int(stats.get("pending") or 0)
        retrying = int(stats.get("retrying") or 0)
        OCR_QUEUE_BACKLOG.set(pending + retrying)
        row = IngestionQueueService(db).process_next()
        if row:
            logger.info(f"ingestion_queue: id={row.id} status={row.status}")
    finally:
        db.close()


def _run_auto_ingestion_once(logger: logging.Logger) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        result = IngestionService(db).scan_recv_dir(
            job_id=None,
            force_reanalyze=bool(settings.ingestion_auto_force_reanalyze),
        )
        logger.info(f"auto_ingestion: {result}")
    except Exception as exc:
        logger.warning(f"auto_ingestion_failed: {exc}")
    finally:
        db.close()


def _run_communication_dispatch_once(logger: logging.Logger) -> None:
    db = SessionLocal()
    try:
        result = CommunicationDispatcherService(db).dispatch_due()
        processed = int(result.get("processed") or 0)
        if processed:
            logger.info(
                f"communication_dispatch: processed={processed} sent={result.get('sent', 0)} failed={result.get('failed', 0)}"
            )
    finally:
        db.close()


def _start_alerts_evaluator() -> None:
    settings = get_settings()
    if not settings.alerts_eval_enabled:
        return
    interval = max(30, int(settings.alerts_eval_interval_seconds or 60))
    logger = logging.getLogger("uvicorn.error")

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval)
                await asyncio.to_thread(_run_alert_eval_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _run_alert_eval_once(logger: logging.Logger) -> None:
    db = SessionLocal()
    try:
        alerts = collect_active_alerts(db)
        if alerts:
            logger.warning(f"alerts_active={len(alerts)} details={alerts}")
    finally:
        db.close()


def _start_lgpd_retention_scheduler() -> None:
    settings = get_settings()
    if not settings.lgpd_retention_auto_enabled:
        return
    interval_h = max(6, int(settings.lgpd_retention_interval_hours or 24))
    logger = logging.getLogger("uvicorn.error")

    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval_h * 3600)
                await asyncio.to_thread(_run_lgpd_retention_once, logger)
            except Exception:
                continue

    asyncio.create_task(_loop())


def _run_lgpd_retention_once(logger: logging.Logger) -> None:
    db = SessionLocal()
    try:
        result = run_retention_cycle(db, older_than_days=get_settings().lgpd_default_retention_days, limit=300)
        logger.info(f"lgpd_retention: {result}")
    finally:
        db.close()


def _run_missing_cleanup_once(logger: logging.Logger) -> None:
    from pathlib import Path
    from sqlalchemy import select
    from app.models.resume import Resume
    from datetime import datetime

    db = SessionLocal()
    try:
        updated = 0
        rows = db.execute(select(Resume).where(Resume.missing_in_storage.is_(False))).scalars().all()
        for r in rows:
            if not Path(r.file_path).exists():
                r.missing_in_storage = True
                r.missing_at = datetime.utcnow()
                db.add(r)
                updated += 1
        db.commit()
        if updated:
            logger.info(f"missing_cleanup: updated={updated}")
    finally:
        db.close()

def _ensure_schema_upgrade() -> None:
    try:
        with engine.begin() as conn:
            def _cols(table: str) -> set[str]:
                out: set[str] = set()
                res = conn.exec_driver_sql(f"PRAGMA table_info('{table}')")
                for row in res.fetchall():
                    out.add(row[1])
                return out

            cols = set()
            cols = _cols("jobs")
            upgrades = []
            if "closed_at" not in cols:
                upgrades.append("ALTER TABLE jobs ADD COLUMN closed_at TEXT")
            if "close_reason" not in cols:
                upgrades.append("ALTER TABLE jobs ADD COLUMN close_reason TEXT")
            if "deleted" not in cols:
                upgrades.append("ALTER TABLE jobs ADD COLUMN deleted INTEGER DEFAULT 0")
            if "ranking_profile" not in cols:
                upgrades.append("ALTER TABLE jobs ADD COLUMN ranking_profile TEXT")
            for sql in upgrades:
                conn.exec_driver_sql(sql)

            rcols = _cols("resumes")
            if "department" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN department TEXT")
            if "department_id" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN department_id INTEGER")
            if "missing_in_storage" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN missing_in_storage INTEGER DEFAULT 0")
            if "missing_at" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN missing_at TEXT")
            if "structured_json" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN structured_json TEXT")
            if "extraction_confidence" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN extraction_confidence REAL")
            if "requires_manual_review" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN requires_manual_review INTEGER DEFAULT 0")
            if "review_reason" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN review_reason TEXT")
            if "filename_cargo" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN filename_cargo TEXT")
            if "filename_cnh" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN filename_cnh TEXT")
            if "filename_date" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN filename_date TEXT")
            if "imported_at" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN imported_at TEXT")
            if "last_synced_at" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN last_synced_at TEXT")
            if "processing_status" not in rcols:
                conn.exec_driver_sql("ALTER TABLE resumes ADD COLUMN processing_status TEXT")

            ccols = _cols("candidates")
            if "address" not in ccols:
                conn.exec_driver_sql("ALTER TABLE candidates ADD COLUMN address TEXT")
            if "linkedin" not in ccols:
                conn.exec_driver_sql("ALTER TABLE candidates ADD COLUMN linkedin TEXT")

            acols = _cols("applications")
            if "primary_role" not in acols:
                conn.exec_driver_sql("ALTER TABLE applications ADD COLUMN primary_role TEXT")
            if "secondary_roles_json" not in acols:
                conn.exec_driver_sql("ALTER TABLE applications ADD COLUMN secondary_roles_json TEXT")
            if "role_confidence" not in acols:
                conn.exec_driver_sql("ALTER TABLE applications ADD COLUMN role_confidence REAL")

            # ingestion_jobs
            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT,
                    job_id INTEGER,
                    force_reanalyze INTEGER DEFAULT 0,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    requested_by TEXT,
                    requested_ip TEXT,
                    requested_at TEXT,
                    next_attempt_at TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    result_json TEXT,
                    error_message TEXT
                )
                """
            )
            ijcols = _cols("ingestion_jobs")
            if "attempts" not in ijcols:
                conn.exec_driver_sql("ALTER TABLE ingestion_jobs ADD COLUMN attempts INTEGER DEFAULT 0")
            if "max_attempts" not in ijcols:
                conn.exec_driver_sql("ALTER TABLE ingestion_jobs ADD COLUMN max_attempts INTEGER DEFAULT 3")
            if "next_attempt_at" not in ijcols:
                conn.exec_driver_sql("ALTER TABLE ingestion_jobs ADD COLUMN next_attempt_at TEXT")

            # communication_events
            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS communication_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER,
                    channel TEXT,
                    message_id TEXT,
                    event_type TEXT,
                    status TEXT,
                    template_name TEXT,
                    subject TEXT,
                    body TEXT,
                    payload_json TEXT,
                    attempts INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    next_attempt_at TEXT,
                    error_message TEXT,
                    scheduled_for TEXT,
                    sent_at TEXT,
                    created_by TEXT,
                    created_at TEXT
                )
                """
            )
            cecols = _cols("communication_events")
            if "message_id" not in cecols:
                conn.exec_driver_sql("ALTER TABLE communication_events ADD COLUMN message_id TEXT")
            if "attempts" not in cecols:
                conn.exec_driver_sql("ALTER TABLE communication_events ADD COLUMN attempts INTEGER DEFAULT 0")
            if "max_attempts" not in cecols:
                conn.exec_driver_sql("ALTER TABLE communication_events ADD COLUMN max_attempts INTEGER DEFAULT 3")
            if "next_attempt_at" not in cecols:
                conn.exec_driver_sql("ALTER TABLE communication_events ADD COLUMN next_attempt_at TEXT")
            if "error_message" not in cecols:
                conn.exec_driver_sql("ALTER TABLE communication_events ADD COLUMN error_message TEXT")
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_comm_message_id_uq ON communication_events(message_id)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS dead_letter_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_queue TEXT,
                    source_id TEXT,
                    reason TEXT,
                    payload_json TEXT,
                    status TEXT,
                    reprocessed_at TEXT,
                    created_at TEXT
                )
                """
            )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_dead_letter_status ON dead_letter_events(status)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS resume_change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resume_id INTEGER,
                    action TEXT,
                    old_value_json TEXT,
                    new_value_json TEXT,
                    reason TEXT,
                    actor TEXT,
                    created_at TEXT
                )
                """
            )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_resume_history_resume ON resume_change_history(resume_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_resume_history_created ON resume_change_history(created_at)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS candidate_consents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER,
                    channel TEXT,
                    status TEXT,
                    source TEXT,
                    note TEXT,
                    updated_by TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_consent_uq ON candidate_consents(candidate_id, channel)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS candidate_pii_vault (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER,
                    email_enc TEXT,
                    phone_enc TEXT,
                    address_enc TEXT,
                    linkedin_enc TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_pii_vault_uq ON candidate_pii_vault(candidate_id)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS matching_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    candidate_id INTEGER,
                    application_id INTEGER,
                    decision TEXT,
                    expected_score REAL,
                    reviewer TEXT,
                    notes TEXT,
                    created_at TEXT
                )
                """
            )

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS matching_calibrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    department TEXT,
                    score_multiplier REAL,
                    score_bias REAL,
                    min_score_floor REAL,
                    notes TEXT,
                    updated_by TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS idx_matching_calibration_scope_uq ON matching_calibrations(job_id, department)")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS stage_automation_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER,
                    from_stage TEXT,
                    to_stage TEXT,
                    channel TEXT,
                    template_name TEXT,
                    delay_minutes INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    variables_json TEXT,
                    created_by TEXT,
                    created_at TEXT
                )
                """
            )

            mtcols = _cols("message_templates")
            if "version" not in mtcols:
                conn.exec_driver_sql("ALTER TABLE message_templates ADD COLUMN version INTEGER DEFAULT 1")
            if "status" not in mtcols:
                conn.exec_driver_sql("ALTER TABLE message_templates ADD COLUMN status TEXT DEFAULT 'draft'")
            if "parent_id" not in mtcols:
                conn.exec_driver_sql("ALTER TABLE message_templates ADD COLUMN parent_id INTEGER")
            if "approved_by" not in mtcols:
                conn.exec_driver_sql("ALTER TABLE message_templates ADD COLUMN approved_by TEXT")
            if "approved_at" not in mtcols:
                conn.exec_driver_sql("ALTER TABLE message_templates ADD COLUMN approved_at TEXT")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_template_status ON message_templates(status)")
    except Exception:
        pass
