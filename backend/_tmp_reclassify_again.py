from types import SimpleNamespace
from app.core.db import SessionLocal
from app.api.routes.resumes import reclassify_false_young_apprentice

req = SimpleNamespace(client=None)
db = SessionLocal()
try:
    dry = reclassify_false_young_apprentice(request=req, dry_run=True, relink_applications=True, limit=5000, db=db)
    print('DRY', dry)
    run = reclassify_false_young_apprentice(request=req, dry_run=False, relink_applications=True, limit=5000, db=db)
    print('RUN', run)
finally:
    db.close()
