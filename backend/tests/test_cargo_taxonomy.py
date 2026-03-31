import unittest
import tempfile
from pathlib import Path as SysPath

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.cargo_taxonomy as cargo_taxonomy
from app.services.cargo_taxonomy import apply_role_feedback, classify_roles, get_role_feedback_profile
from app.services.resume_structuring import structure_resume_text


class CargoTaxonomyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_profile_path = cargo_taxonomy.ROLE_FEEDBACK_PROFILE_PATH
        cargo_taxonomy.ROLE_FEEDBACK_PROFILE_PATH = SysPath(self._tmp.name) / "role_feedback_profile.json"

    def tearDown(self):
        cargo_taxonomy.ROLE_FEEDBACK_PROFILE_PATH = self._old_profile_path
        self._tmp.cleanup()

    def test_classify_motorista_role(self):
        text = "Atuou como motorista de ônibus urbano, CNH D, transporte coletivo."
        result = classify_roles(text)
        self.assertEqual(result["primary_role"], "Motorista")
        self.assertGreaterEqual(result["confidence"], 0.35)
        self.assertIn("needs_review", result)

    def test_structuring_contains_field_confidence(self):
        text = """
        Maria Souza
        email: maria@empresa.com
        experiência de 3 anos em atendimento
        """
        result = structure_resume_text(text=text, fallback_name=None)
        quality = result["quality"]
        self.assertIn("field_confidence", quality)
        self.assertIn("contato", quality["field_confidence"])
        self.assertIn("classificacao_cargo", quality["field_confidence"])

    def test_apply_role_feedback_persists_profile(self):
        apply_role_feedback(correct_role="Motorista", predicted_role="Atendimento")
        profile = get_role_feedback_profile()
        self.assertGreater(profile["stats"]["total_feedback"], 0)
        self.assertGreater(profile["role_bias"].get("Motorista", 0), 0)


if __name__ == "__main__":
    unittest.main()
