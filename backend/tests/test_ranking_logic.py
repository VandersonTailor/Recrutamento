import unittest
from datetime import datetime, timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.application import Application
from app.models.job import Job
from app.services.match import compute_match
from app.services.ranking import RankingService


class RankingLogicTests(unittest.TestCase):
    def test_keyword_stuffing_penalty_applied(self):
        job = Job(title="Auxiliar de Manutencao", requirements="manutencao eletrica oficina nr10")
        repeated = ("manutencao " * 90) + ("eletrica " * 60) + ("oficina " * 40)
        app = Application(
            analysis_json=repeated,
            score_justification="",
            strengths="",
            concerns="",
            seniority="Indefinido",
        )
        result = compute_match(app, job, resume_text=repeated)
        self.assertGreater(result.stuffing_penalty, 0.0)
        self.assertLessEqual(result.total, 100.0)

    def test_simple_profile_bonus_applied(self):
        job = Job(title="Motorista", requirements="cnh d experiencia")
        app = Application(
            analysis_json="curriculo simples",
            score_justification="",
            strengths="",
            concerns="",
            seniority="Indefinido",
        )
        structured = {
            "fields": {
                "tempo_experiencia_anos": 4,
                "cnh_categoria": "D",
                "areas_experiencia": ["transporte"],
                "experiencias_profissionais": [{"descricao": "Motorista urbano"}],
            },
            "quality": {"confidence": 0.5},
        }
        result = compute_match(app, job, resume_text="simples", resume_structured=structured)
        self.assertGreater(result.simple_profile_bonus, 0.0)

    def test_deterministic_tie_break(self):
        svc = RankingService(db=None)  # type: ignore[arg-type]
        now = datetime.utcnow()
        a = {
            "match_percent": 80,
            "role_confidence": 0.6,
            "experience_years": 3,
            "updated_at": now,
            "candidate_id": 2,
        }
        b = {
            "match_percent": 80,
            "role_confidence": 0.7,
            "experience_years": 2,
            "updated_at": now - timedelta(hours=1),
            "candidate_id": 1,
        }
        self.assertGreater(svc._rank_sort_key(b), svc._rank_sort_key(a))

    def test_rank_reason_is_assigned(self):
        svc = RankingService(db=None)  # type: ignore[arg-type]
        items = [
            {"match_percent": 90, "role_confidence": 0.8, "experience_years": 5, "updated_at": datetime.utcnow(), "candidate_id": 1},
            {"match_percent": 90, "role_confidence": 0.6, "experience_years": 6, "updated_at": datetime.utcnow(), "candidate_id": 2},
        ]
        items.sort(key=svc._rank_sort_key, reverse=True)
        svc._annotate_rank_reasons(items)
        self.assertEqual(items[0]["rank_position"], 1)
        self.assertIsNotNone(items[1].get("rank_reason"))


if __name__ == "__main__":
    unittest.main()
