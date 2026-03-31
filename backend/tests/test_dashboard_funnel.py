import unittest
from datetime import datetime, timedelta

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import Base
from app.models.stage_history import StageHistory
from app.services.dashboard import _build_stage_funnel


class DashboardFunnelTests(unittest.TestCase):
    def test_build_stage_funnel_computes_conversion(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        now = datetime.utcnow()

        with Session(engine) as db:
            # App 1 avança de Recebido -> Em análise -> Pré-selecionado
            db.add(StageHistory(application_id=1, from_stage=None, to_stage="Recebido", changed_at=now))
            db.add(StageHistory(application_id=1, from_stage="Recebido", to_stage="Em análise", changed_at=now + timedelta(hours=4)))
            db.add(StageHistory(application_id=1, from_stage="Em análise", to_stage="Pré-selecionado", changed_at=now + timedelta(hours=8)))
            # App 2 cai para Reprovado após Recebido
            db.add(StageHistory(application_id=2, from_stage=None, to_stage="Recebido", changed_at=now + timedelta(minutes=5)))
            db.add(StageHistory(application_id=2, from_stage="Recebido", to_stage="Reprovado", changed_at=now + timedelta(hours=3)))
            db.commit()

            funnel = _build_stage_funnel(db)

        recebido = next(row for row in funnel if row["stage"] == "Recebido")
        self.assertEqual(recebido["entered"], 2)
        self.assertEqual(recebido["advanced"], 1)
        self.assertEqual(recebido["conversion_rate"], 50.0)
        self.assertEqual(recebido["dropoff_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()
