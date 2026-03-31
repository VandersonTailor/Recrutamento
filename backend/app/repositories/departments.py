from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.department import Department


class DepartmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: str) -> Department | None:
        stmt = select(Department).where(Department.name == name)
        return self.db.execute(stmt).scalars().first()

    def upsert(self, name: str, path: str | None) -> Department:
        dep = self.get_by_name(name)
        if dep:
            if path and dep.path != path:
                dep.path = path
                self.db.add(dep)
                self.db.commit()
            return dep
        dep = Department(name=name, path=path)
        self.db.add(dep)
        self.db.commit()
        self.db.refresh(dep)
        return dep
