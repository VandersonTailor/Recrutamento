from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.candidate import Candidate
from app.models.common import ApplicationStage
from app.models.job import Job
from app.models.processing_log import ProcessingLog
from app.models.resume import Resume
from app.models.stage_history import StageHistory
from datetime import datetime, timedelta


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_stats(self) -> dict:
        total_resumes = self.db.execute(select(func.count(Resume.id)).where(Resume.missing_in_storage.is_(False))).scalar_one()
        total_open_jobs = self.db.execute(select(func.count(Job.id)).where(Job.is_active.is_(True), Job.deleted.is_(False))).scalar_one()
        total_applications = self.db.execute(select(func.count(Application.id))).scalar_one()

        resumes_by_channel = [
            {"channel": row[0], "count": int(row[1])}
            for row in self.db.execute(
                select(Resume.source_channel, func.count(Resume.id))
                .where(Resume.missing_in_storage.is_(False))
                .group_by(Resume.source_channel)
            ).all()
        ]

        applications_by_stage = [
            {"stage": row[0], "count": int(row[1])}
            for row in self.db.execute(
                select(Application.stage, func.count(Application.id)).group_by(Application.stage)
            ).all()
        ]

        resumes_by_job = [
            {"job_id": row[0], "job_title": row[1], "count": int(row[2])}
            for row in self.db.execute(
                select(Job.id, Job.title, func.count(Application.id))
                .select_from(Job)
                .join(Application, Application.job_id == Job.id, isouter=True)
                .group_by(Job.id, Job.title)
                .order_by(func.count(Application.id).desc())
            ).all()
        ]

        # Tempo médio de contratação: diferença entre primeiro histórico e mudança para 'Aprovado'
        avg_days_to_hire = None
        try:
            approved_histories = self.db.execute(
                select(StageHistory.application_id, StageHistory.changed_at).where(StageHistory.to_stage == "Aprovado")
            ).all()
            if approved_histories:
                total_days = 0.0
                count = 0
                for app_id, approved_at in approved_histories:
                    first_hist = self.db.execute(
                        select(StageHistory.changed_at)
                        .where(StageHistory.application_id == app_id)
                        .order_by(StageHistory.changed_at.asc())
                        .limit(1)
                    ).scalar_one_or_none()
                    if first_hist and approved_at:
                        delta = approved_at - first_hist
                        total_days += delta.total_seconds() / 86400.0
                        count += 1
                if count:
                    avg_days_to_hire = round(total_days / count, 2)
        except Exception:
            avg_days_to_hire = None

        # Conversão por etapa: proporção relativa ao total
        total_stages = sum(s["count"] for s in applications_by_stage) or 1
        conversion_by_stage = [
            {"stage": s["stage"], "rate": round(100.0 * s["count"] / total_stages, 2), "count": s["count"]}
            for s in applications_by_stage
        ]
        funnel_by_stage = _build_stage_funnel(self.db)

        # Desempenho mensal: contratações (Aprovado) por mês (últimos 6 meses)
        now = datetime.utcnow()
        month_points = []
        for i in range(6, -1, -1):
            start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = (start + timedelta(days=31)).replace(day=1)
            count_approved = self.db.execute(
                select(func.count(StageHistory.id)).where(
                    StageHistory.to_stage == "Aprovado",
                    StageHistory.changed_at >= start,
                    StageHistory.changed_at < end,
                )
            ).scalar_one()
            month_points.append({"month": start.strftime("%Y-%m"), "approved": int(count_approved)})

        return {
            "total_resumes": int(total_resumes),
            "total_open_jobs": int(total_open_jobs),
            "total_applications": int(total_applications),
            "resumes_by_job": resumes_by_job,
            "resumes_by_channel": resumes_by_channel,
            "applications_by_stage": applications_by_stage,
            "avg_days_to_hire": avg_days_to_hire,
            "conversion_by_stage": conversion_by_stage,
            "funnel_by_stage": funnel_by_stage,
            "monthly_performance": month_points,
        }

    def get_diagnostics(self) -> dict:
        total_logs = int(self.db.execute(select(func.count(ProcessingLog.id))).scalar_one() or 0)
        success_logs = int(
            self.db.execute(select(func.count(ProcessingLog.id)).where(ProcessingLog.status == "success")).scalar_one() or 0
        )

        avg_duration = self.db.execute(
            select(func.avg(ProcessingLog.duration_ms)).where(ProcessingLog.duration_ms.is_not(None))
        ).scalar_one_or_none()
        avg_duration_val = float(round(float(avg_duration or 0.0), 2))

        durations = [
            int(v)
            for v in self.db.execute(
                select(ProcessingLog.duration_ms).where(ProcessingLog.duration_ms.is_not(None)).order_by(ProcessingLog.duration_ms.asc())
            )
            .scalars()
            .all()
            if v is not None
        ]
        p95 = None
        if durations:
            idx = min(len(durations) - 1, max(0, int(round((len(durations) - 1) * 0.95))))
            p95 = float(durations[idx])

        total_resumes = int(self.db.execute(select(func.count(Resume.id))).scalar_one() or 0)
        missing_resumes = int(
            self.db.execute(select(func.count(Resume.id)).where(Resume.missing_in_storage.is_(True))).scalar_one() or 0
        )
        resumes_with_text = int(
            self.db.execute(
                select(func.count(Resume.id)).where(Resume.extracted_text.is_not(None), Resume.extracted_text != "")
            ).scalar_one()
            or 0
        )
        review_required = int(
            self.db.execute(select(func.count(Resume.id)).where(Resume.requires_manual_review.is_(True))).scalar_one() or 0
        )
        review_pending_24h = int(
            self.db.execute(
                select(func.count(Resume.id)).where(
                    Resume.requires_manual_review.is_(True),
                    Resume.received_at <= (datetime.utcnow() - timedelta(hours=24)),
                )
            ).scalar_one()
            or 0
        )
        review_pending_72h = int(
            self.db.execute(
                select(func.count(Resume.id)).where(
                    Resume.requires_manual_review.is_(True),
                    Resume.received_at <= (datetime.utcnow() - timedelta(hours=72)),
                )
            ).scalar_one()
            or 0
        )

        avg_review_resolution_hours = self._avg_review_resolution_hours()

        candidates_total = int(self.db.execute(select(func.count(Candidate.id))).scalar_one() or 0)
        with_email = int(self.db.execute(select(func.count(Candidate.id)).where(Candidate.email.is_not(None))).scalar_one() or 0)
        with_phone = int(self.db.execute(select(func.count(Candidate.id)).where(Candidate.phone.is_not(None))).scalar_one() or 0)
        with_any_contact = int(
            self.db.execute(
                select(func.count(Candidate.id)).where((Candidate.email.is_not(None)) | (Candidate.phone.is_not(None)))
            ).scalar_one()
            or 0
        )

        return {
            "total_processing_logs": total_logs,
            "processing_success_rate": round((100.0 * success_logs / max(1, total_logs)), 2),
            "processing_avg_duration_ms": avg_duration_val,
            "processing_p95_duration_ms": p95,
            "resumes_missing_in_storage": missing_resumes,
            "resumes_with_extracted_text": resumes_with_text,
            "extraction_coverage_rate": round((100.0 * resumes_with_text / max(1, total_resumes)), 2),
            "resumes_requires_manual_review": review_required,
            "manual_review_rate": round((100.0 * review_required / max(1, total_resumes)), 2),
            "review_pending_over_24h": review_pending_24h,
            "review_pending_over_72h": review_pending_72h,
            "avg_review_resolution_hours": avg_review_resolution_hours,
            "candidates_with_email": with_email,
            "candidates_with_phone": with_phone,
            "candidates_with_contact_rate": round(
                100.0 * with_any_contact / max(1, candidates_total),
                2,
            ),
        }

    def _avg_review_resolution_hours(self) -> float | None:
        # Aproximação de SLA: momento do recebimento do currículo até o primeiro
        # evento de aprovação de revisão manual no audit log.
        rows = self.db.execute(
            select(AuditLog.resource_id, AuditLog.created_at, AuditLog.metadata_json)
            .where(AuditLog.action == "resumes.structured.update")
            .order_by(AuditLog.created_at.asc())
        ).all()
        if not rows:
            return None

        totals = 0.0
        count = 0
        seen: set[int] = set()
        for resource_id, reviewed_at, metadata_json in rows:
            if metadata_json and '"approve_review": true' not in metadata_json.lower():
                continue
            try:
                rid = int(resource_id)
            except Exception:
                continue
            if rid in seen:
                continue
            resume = self.db.get(Resume, rid)
            if not resume or not resume.received_at:
                continue
            delta = reviewed_at - resume.received_at
            hours = delta.total_seconds() / 3600.0
            if hours >= 0:
                totals += hours
                count += 1
                seen.add(rid)
        if count == 0:
            return None
        return round(totals / count, 2)


FLOW_SEQUENCE = [
    ApplicationStage.recebido.value,
    ApplicationStage.em_analise.value,
    ApplicationStage.pre_selecionado.value,
    ApplicationStage.entrevista.value,
    ApplicationStage.teste_tecnico.value,
    ApplicationStage.aprovado.value,
]


def _build_stage_funnel(db: Session) -> list[dict]:
    histories = db.execute(
        select(StageHistory).order_by(StageHistory.application_id.asc(), StageHistory.changed_at.asc())
    ).scalars().all()
    if not histories:
        return [
            {
                "stage": stage,
                "next_stage": FLOW_SEQUENCE[idx + 1] if idx + 1 < len(FLOW_SEQUENCE) else None,
                "entered": 0,
                "advanced": 0,
                "conversion_rate": 0.0,
                "dropoff_rate": 0.0,
                "talent_pool_rate": 0.0,
                "avg_time_to_next_hours": None,
            }
            for idx, stage in enumerate(FLOW_SEQUENCE)
        ]

    entered_map = {stage: 0 for stage in FLOW_SEQUENCE}
    advanced_map = {stage: 0 for stage in FLOW_SEQUENCE}
    dropoff_map = {stage: 0 for stage in FLOW_SEQUENCE}
    talent_pool_map = {stage: 0 for stage in FLOW_SEQUENCE}
    elapsed_hours_map = {stage: [] for stage in FLOW_SEQUENCE}

    by_app: dict[int, list[StageHistory]] = {}
    for row in histories:
        by_app.setdefault(row.application_id, []).append(row)

    for rows in by_app.values():
        for idx, row in enumerate(rows):
            stage = row.to_stage
            if stage in entered_map:
                entered_map[stage] += 1
            if idx >= len(rows) - 1 or stage not in entered_map:
                continue

            nxt = rows[idx + 1]
            hours = round(max(0.0, (nxt.changed_at - row.changed_at).total_seconds() / 3600.0), 2)
            elapsed_hours_map[stage].append(hours)

            expected_next = FLOW_SEQUENCE[FLOW_SEQUENCE.index(stage) + 1] if stage != FLOW_SEQUENCE[-1] else None
            if expected_next and nxt.to_stage == expected_next:
                advanced_map[stage] += 1
            if nxt.to_stage == ApplicationStage.reprovado.value:
                dropoff_map[stage] += 1
            if nxt.to_stage == ApplicationStage.banco_talentos.value:
                talent_pool_map[stage] += 1

    out = []
    for idx, stage in enumerate(FLOW_SEQUENCE):
        entered = entered_map[stage]
        advanced = advanced_map[stage]
        dropoff = dropoff_map[stage]
        talent = talent_pool_map[stage]
        avg_time = None
        if elapsed_hours_map[stage]:
            avg_time = round(sum(elapsed_hours_map[stage]) / len(elapsed_hours_map[stage]), 2)

        out.append(
            {
                "stage": stage,
                "next_stage": FLOW_SEQUENCE[idx + 1] if idx + 1 < len(FLOW_SEQUENCE) else None,
                "entered": entered,
                "advanced": advanced,
                "conversion_rate": round((advanced / entered) * 100.0, 2) if entered else 0.0,
                "dropoff_rate": round((dropoff / entered) * 100.0, 2) if entered else 0.0,
                "talent_pool_rate": round((talent / entered) * 100.0, 2) if entered else 0.0,
                "avg_time_to_next_hours": avg_time,
            }
        )
    return out
