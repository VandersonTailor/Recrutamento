import unittest

import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import current_role, require_roles


class SecurityRolesTests(unittest.TestCase):
    def test_current_role_normalization(self):
        self.assertEqual(current_role("ADMIN"), "admin")
        self.assertEqual(current_role("manager"), "manager")
        self.assertEqual(current_role("xpto"), "viewer")
        self.assertEqual(current_role(None), "viewer")

    def test_require_roles_allows_authorized(self):
        dep = require_roles("manager", "admin")
        self.assertEqual(dep("admin"), "admin")
        self.assertEqual(dep("manager"), "manager")

    def test_require_roles_blocks_unauthorized(self):
        dep = require_roles("admin")
        with self.assertRaises(HTTPException):
            dep("viewer")


if __name__ == "__main__":
    unittest.main()
