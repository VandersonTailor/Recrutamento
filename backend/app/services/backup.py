import hashlib
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.resume import Resume


class BackupService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def run(self) -> dict:
        if not self.settings.backup_enabled:
            return {"status": "disabled", "copied": 0, "skipped": 0, "errors": 0}

        backup_dir = self.settings.backup_dir_path()
        recv_dir = self.settings.recv_dir_path()
        try:
            backup_dir.resolve().relative_to(recv_dir.resolve())
        except Exception:
            pass
        else:
            raise ValueError("backup_dir não pode ficar dentro de recv_dir")
        backup_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        errors = 0

        rows = self.db.execute(select(Resume.file_path, Resume.file_hash)).all()
        for file_path, file_hash in rows:
            try:
                src = Path(str(file_path))
                if not src.exists() or not src.is_file():
                    errors += 1
                    continue

                ext = src.suffix.lower()
                dst = backup_dir / f"{file_hash}{ext}"
                if dst.exists():
                    skipped += 1
                    continue

                tmp = dst.with_suffix(dst.suffix + ".tmp")
                shutil.copy2(str(src), str(tmp))
                _verify_hash(tmp, file_hash)
                tmp.replace(dst)
                copied += 1
            except Exception:
                errors += 1
                continue

        return {"status": "ok", "copied": copied, "skipped": skipped, "errors": errors}


def _verify_hash(path: Path, expected_hash: str) -> None:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected_hash:
        raise ValueError("Hash do backup não confere")
