import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.application import Application
from app.models.job import Job
from app.services.match import compute_match
from app.services.scoring import apply_feedback_to_profile, read_scoring_profile, store_scoring_profile


class ScoringProfileTests(unittest.TestCase):
    def test_store_and_read_profile_normalizes_weights(self):
        job = Job(title="Auxiliar de Manutenção")
        payload = {
            "weights": {
                "cargo": 3,
                "formacao": 2,
                "cursos": 3,
                "experiencia": 2,
            },
            "porto_alegre_bonus": 10,
            "minimum_signal_floor": 15,
        }
        stored = store_scoring_profile(job, payload)
        profile = read_scoring_profile(job)

        self.assertAlmostEqual(sum(stored["weights"].values()), 1.0, places=5)
        self.assertEqual(profile["porto_alegre_bonus"], 10.0)
        self.assertEqual(profile["minimum_signal_floor"], 15.0)

    def test_compute_match_uses_configured_bonus(self):
        app = Application(
            analysis_json="motorista cnh d experiencia 5 anos",
            score_justification="bom alinhamento",
            strengths="CNH D",
            concerns=None,
            seniority="Pleno",
        )
        job = Job(
            title="Motorista",
            description="Condução de ônibus",
            requirements="CNH D e experiência",
        )
        profile = {
            "weights": {"cargo": 0.25, "formacao": 0.15, "cursos": 0.20, "experiencia": 0.40},
            "porto_alegre_bonus": 12.0,
            "minimum_signal_floor": 10.0,
        }

        result = compute_match(
            app,
            job,
            resume_text="Residente em Porto Alegre/RS com experiência em transporte.",
            candidate_address="Porto Alegre - RS",
            scoring_profile=profile,
        )
        self.assertGreaterEqual(result.localizacao_bonus, 12.0)
        self.assertGreater(result.total, 0.0)

    def test_role_based_default_profile_for_motorista(self):
        job = Job(title="Motorista de ônibus")
        profile = read_scoring_profile(job)
        self.assertEqual(profile.get("role_hint"), "Motorista")
        self.assertAlmostEqual(profile["weights"]["cargo"], 0.35, places=3)
        self.assertAlmostEqual(profile["weights"]["experiencia"], 0.35, places=3)

    def test_apply_feedback_updates_weights(self):
        profile = {
            "weights": {"cargo": 0.3, "formacao": 0.2, "cursos": 0.25, "experiencia": 0.25},
            "porto_alegre_bonus": 8.0,
            "minimum_signal_floor": 12.0,
        }
        signal = {"cargo": 0.8, "formacao": 0.3, "cursos": 0.6, "experiencia": 0.7}
        updated = apply_feedback_to_profile(profile=profile, signal=signal, decision="approved", alpha=0.2)
        self.assertAlmostEqual(sum(updated["weights"].values()), 1.0, places=5)
        self.assertGreater(updated["weights"]["cargo"], profile["weights"]["cargo"])
        self.assertIn("feedback_stats", updated)


if __name__ == "__main__":
    unittest.main()
