from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.dashboard import DashboardDiagnostics, DashboardStats
from app.services.dashboard import DashboardService


router = APIRouter()


@router.get("", response_model=DashboardStats)
def get_dashboard(
    db: Session = Depends(get_db),
    department: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    service = DashboardService(db)
    # MVP: filtros serão aplicados futuramente; por ora retorna agregados globais
    return service.get_stats()


@router.get("/export")
def export_dashboard(
    db: Session = Depends(get_db),
    format: str = Query(default="csv", pattern="^(csv|html)$"),
    department: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    stats = DashboardService(db).get_stats()
    if format == "csv":
        def _gen():
            yield "metric,value\n"
            for k in ("total_resumes", "total_open_jobs", "total_applications", "avg_days_to_hire"):
                yield f"{k},{stats.get(k) if stats.get(k) is not None else ''}\n"
        from fastapi.responses import StreamingResponse
        return StreamingResponse(_gen(), media_type="text/csv")
    else:
        html = f"""
        <html><body>
        <h1>Relatório Gerencial</h1>
        <p>Total de currículos: {stats.get('total_resumes')}</p>
        <p>Vagas abertas: {stats.get('total_open_jobs')}</p>
        <p>Candidaturas: {stats.get('total_applications')}</p>
        <p>Tempo médio de contratação (dias): {stats.get('avg_days_to_hire') or '-'}</p>
        </body></html>
        """
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)


@router.get("/diagnostics", response_model=DashboardDiagnostics)
def get_dashboard_diagnostics(db: Session = Depends(get_db)):
    return DashboardService(db).get_diagnostics()
