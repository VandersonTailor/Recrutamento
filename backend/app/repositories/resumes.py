from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.resume import Resume


class ResumeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_hash(self, file_hash: str) -> Resume | None:
        stmt = select(Resume).where(Resume.file_hash == file_hash).limit(1)
        return self.db.execute(stmt).scalars().first()

    def create(self, resume: Resume) -> Resume:
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def update(self, resume: Resume) -> Resume:
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def get(self, resume_id: int) -> Resume | None:
        return self.db.get(Resume, resume_id)

    def get_by_path(self, file_path: str) -> Resume | None:
        stmt = select(Resume).where(Resume.file_path == file_path).limit(1)
        return self.db.execute(stmt).scalars().first()
