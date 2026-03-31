import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.resume_structuring import structure_resume_text


class ResumeStructuringTests(unittest.TestCase):
    def test_extracts_core_fields_with_reasonable_confidence(self):
        sample = """
        JOAO DA SILVA
        Email: joao.silva@email.com
        Telefone: (51) 99999-8888
        Porto Alegre - RS
        Objetivo: Vaga de Motorista
        CNH D
        Experiência: atuou 5 anos em transporte coletivo e atendimento.
        Curso NR10 e Excel básico.
        """
        data = structure_resume_text(text=sample, fallback_name=None)
        fields = data["fields"]
        quality = data["quality"]

        self.assertEqual(fields["contato"]["email"], "joao.silva@email.com")
        self.assertIsNotNone(fields["contato"]["telefone"])
        self.assertEqual(fields["cidade_regiao"], "Porto Alegre")
        self.assertEqual(fields["cnh_categoria"], "D")
        self.assertGreaterEqual(fields["tempo_experiencia_anos"] or 0, 5)
        self.assertGreaterEqual(quality["confidence"], 0.55)
        self.assertFalse(quality["requires_manual_review"])
        self.assertIn("role_classification_needs_review", quality)

    def test_marks_manual_review_on_low_signal_text(self):
        sample = "curriculo"
        data = structure_resume_text(text=sample, fallback_name="Candidato X")
        quality = data["quality"]
        self.assertTrue(quality["requires_manual_review"])
        self.assertLessEqual(quality["confidence"], 0.55)
        self.assertIsNotNone(quality["review_reason"])
        self.assertIn("classificacao", quality["review_reason"])


if __name__ == "__main__":
    unittest.main()
