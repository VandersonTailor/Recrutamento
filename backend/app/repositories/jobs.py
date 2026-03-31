from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, job: Job) -> Job:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, job_id: int) -> Job | None:
        return self.db.get(Job, job_id)

    def list(self, *, active_only: bool = False) -> list[Job]:
        stmt = select(Job).where(Job.deleted.is_(False)).order_by(Job.created_at.desc())
        if active_only:
            stmt = stmt.where(Job.is_active.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def update(self, job: Job) -> Job:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job
