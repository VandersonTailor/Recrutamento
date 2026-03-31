import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.communications import _safe_format


class CommunicationsTests(unittest.TestCase):
    def test_safe_format_keeps_missing_placeholder(self):
        rendered = _safe_format("Olá {candidate_name}, etapa {application_stage}, vaga {job_title}", {"candidate_name": "Ana"})
        self.assertIn("Ana", rendered)
        self.assertIn("{application_stage}", rendered)
        self.assertIn("{job_title}", rendered)


if __name__ == "__main__":
    unittest.main()
