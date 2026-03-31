from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import require_roles
from app.schemas.search import SearchResponse
from app.services.audit import AuditService
from app.services.search import SearchService


router = APIRouter()


@router.get("", response_model=SearchResponse)
def search(
    request: Request,
    q: str = Query(min_length=2),
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    service = SearchService(db)
    results = service.search(q)
    AuditService(db).log(action="search", ip=request.client.host if request.client else None, metadata={"q": q})
    return {"query": q, "results": results}


@router.get("/semantic", response_model=SearchResponse)
def semantic_search(
    request: Request,
    q: str = Query(min_length=2),
    limit: int = Query(default=30, ge=1, le=200),
    min_score: float = Query(default=0.15, ge=0.0, le=1.0),
    department: str | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("viewer", "recruiter", "manager", "admin")),
):
    service = SearchService(db)
    results = service.semantic_search(q, limit=limit, min_score=min_score, department=department)
    AuditService(db).log(
        action="search.semantic",
        ip=request.client.host if request.client else None,
        metadata={"q": q, "limit": limit, "min_score": min_score, "department": department},
    )
    return {"query": q, "results": results}


@router.get("/duplicates", response_model=SearchResponse)
def duplicate_candidates(
    request: Request,
    threshold: float = Query(default=0.72, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=300),
    max_candidates: int = Query(default=250, ge=20, le=1000),
    department: str | None = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    service = SearchService(db)
    results = service.detect_duplicate_candidates(limit=limit, threshold=threshold, max_candidates=max_candidates, department=department)
    query_label = f"duplicates threshold={threshold}"
    AuditService(db).log(
        action="search.duplicates",
        ip=request.client.host if request.client else None,
        metadata={"threshold": threshold, "limit": limit, "max_candidates": max_candidates, "department": department, "count": len(results)},
    )
    return {"query": query_label, "results": results}


@router.get("/recommendations", response_model=SearchResponse)
def recommend_candidates(
    request: Request,
    job_id: int,
    limit: int = Query(default=30, ge=1, le=200),
    min_score: float = Query(default=0.18, ge=0.0, le=1.0),
    include_existing_applications: bool = False,
    db: Session = Depends(get_db),
    _role: str = Depends(require_roles("recruiter", "manager", "admin")),
):
    service = SearchService(db)
    results = service.recommend_candidates_for_job(
        job_id=job_id,
        limit=limit,
        min_score=min_score,
        include_existing_applications=include_existing_applications,
    )
    AuditService(db).log(
        action="search.recommendations",
        ip=request.client.host if request.client else None,
        metadata={"job_id": job_id, "limit": limit, "min_score": min_score, "count": len(results)},
    )
    return {"query": f"recommendations job_id={job_id}", "results": results}
