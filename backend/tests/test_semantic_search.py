import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.search import _semantic_score_from_vectors, _vectorize


class SemanticSearchTests(unittest.TestCase):
    def test_semantic_score_detects_overlap(self):
        a = _vectorize("motorista onibus cnh d transporte urbano")
        b = _vectorize("vaga para motorista com cnh d")
        score, overlap = _semantic_score_from_vectors(a, b)
        self.assertGreater(score, 0.2)
        self.assertIn("motorista", overlap)

    def test_semantic_score_zero_without_overlap(self):
        a = _vectorize("desenvolvedor python sql backend")
        b = _vectorize("auxiliar limpeza conservacao")
        score, overlap = _semantic_score_from_vectors(a, b)
        self.assertLess(score, 0.15)
        self.assertEqual(overlap, [])


if __name__ == "__main__":
    unittest.main()
