import unittest

import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes.jobs import _parse_iso_datetime


class RankingAuditUtilsTests(unittest.TestCase):
    def test_parse_iso_datetime_accepts_date_time(self):
        parsed = _parse_iso_datetime("2026-03-30T10:15:00", field_name="date_from")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 30)
        self.assertEqual(parsed.hour, 10)

    def test_parse_iso_datetime_accepts_utc_z(self):
        parsed = _parse_iso_datetime("2026-03-30T10:15:00Z", field_name="date_from")
        self.assertIsNotNone(parsed)
        # helper normaliza para datetime sem timezone
        self.assertIsNone(parsed.tzinfo)

    def test_parse_iso_datetime_rejects_invalid(self):
        with self.assertRaises(HTTPException):
            _parse_iso_datetime("30/03/2026", field_name="date_from")


if __name__ == "__main__":
    unittest.main()
