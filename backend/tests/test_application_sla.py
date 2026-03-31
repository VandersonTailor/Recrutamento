import unittest
from datetime import datetime, timedelta

import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.applications import _compute_stage_sla, _validate_stage
from app.models.common import ApplicationStage


class ApplicationSLATests(unittest.TestCase):
    def test_compute_stage_sla_overdue(self):
        entered = datetime.utcnow() - timedelta(hours=30)
        sla, elapsed, overdue, overdue_hours = _compute_stage_sla(ApplicationStage.recebido.value, stage_entered_at=entered)
        self.assertEqual(sla, 24)
        self.assertTrue((elapsed or 0) >= 30)
        self.assertTrue(overdue)
        self.assertTrue((overdue_hours or 0) >= 6)

    def test_compute_stage_sla_none_for_terminal_stage(self):
        entered = datetime.utcnow() - timedelta(hours=200)
        sla, elapsed, overdue, overdue_hours = _compute_stage_sla(ApplicationStage.aprovado.value, stage_entered_at=entered)
        self.assertIsNone(sla)
        self.assertIsNone(elapsed)
        self.assertIsNone(overdue)
        self.assertIsNone(overdue_hours)

    def test_validate_stage_rejects_invalid(self):
        with self.assertRaises(HTTPException):
            _validate_stage("Etapa inválida")


if __name__ == "__main__":
    unittest.main()
