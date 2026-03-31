import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ingestion_queue import _backoff_delay


class IngestionQueueTests(unittest.TestCase):
    def test_backoff_increases_with_attempts(self):
        d1 = _backoff_delay(1).total_seconds()
        d2 = _backoff_delay(2).total_seconds()
        d3 = _backoff_delay(3).total_seconds()
        self.assertTrue(d2 >= d1)
        self.assertTrue(d3 >= d2)

    def test_backoff_is_capped(self):
        d = _backoff_delay(20).total_seconds()
        self.assertLessEqual(d, 900)


if __name__ == "__main__":
    unittest.main()
