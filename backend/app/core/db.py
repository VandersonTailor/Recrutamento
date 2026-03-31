from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.database_url.startswith("sqlite:///"):
    sqlite_path = settings.database_url.removeprefix("sqlite:///")
    if sqlite_path.startswith("./") or sqlite_path.startswith(".\\"):
        sqlite_file = Path(__file__).resolve().parents[2] / sqlite_path
    else:
        sqlite_file = Path(sqlite_path)
    sqlite_file.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, class_=Session, autocommit=False, autoflush=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
