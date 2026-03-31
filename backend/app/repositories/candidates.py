from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, candidate_id: int) -> Candidate | None:
        return self.db.get(Candidate, candidate_id)

    def list(self, *, limit: int = 50, offset: int = 0) -> list[Candidate]:
        stmt = select(Candidate).order_by(Candidate.created_at.desc()).offset(offset).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    def find(self, *, email: str | None, phone: str | None, full_name: str | None) -> Candidate | None:
        clauses = []
        if email:
            clauses.append(Candidate.email == email)
        if phone:
            clauses.append(Candidate.phone == phone)
        if full_name:
            clauses.append(Candidate.full_name == full_name)
        if not clauses:
            return None
        stmt = select(Candidate).where(or_(*clauses)).limit(1)
        return self.db.execute(stmt).scalars().first()

    def create(self, candidate: Candidate) -> Candidate:
        self.db.add(candidate)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate
