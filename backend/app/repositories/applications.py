from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, application_id: int) -> Application | None:
        return self.db.get(Application, application_id)

    def get_by_candidate_job(self, *, candidate_id: int, job_id: int) -> Application | None:
        stmt = (
            select(Application)
            .where(Application.candidate_id == candidate_id, Application.job_id == job_id)
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def list_by_job(self, job_id: int) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.job_id == job_id)
            .order_by(Application.score.desc().nullslast(), Application.updated_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_recent(self, *, limit: int = 100) -> list[Application]:
        stmt = select(Application).order_by(Application.updated_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def create(self, application: Application) -> Application:
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application

    def update(self, application: Application) -> Application:
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application
