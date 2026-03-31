import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.resume_view import build_professional_summary, extract_address, extract_email, extract_phone, validate_contact
from app.services.resume_view import extract_linkedin


class ResumeViewExtractionTests(unittest.TestCase):
    def test_extract_email(self):
        text = "Contato: Joao.Silva-1@empresa.com.br\nOutro: x@y.z"
        self.assertEqual(extract_email(text), "joao.silva-1@empresa.com.br")

    def test_extract_phone_formats(self):
        samples = [
            "Tel: (11) 91234-5678",
            "Telefone: 11 91234 5678",
            "Contato: 11912345678",
            "Fone: (21) 2345-6789",
        ]
        for s in samples:
            self.assertIsNotNone(extract_phone(s))

    def test_extract_address(self):
        text = "João Silva\nRua das Flores, 123 - Centro\nCEP 12345-678\nExperiência: ..."
        addr = extract_address(text)
        self.assertIsNotNone(addr)
        self.assertIn("Rua", addr)

    def test_extract_linkedin(self):
        text = "LinkedIn: linkedin.com/in/joao-silva-12345\n"
        url = extract_linkedin(text)
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("https://"))
        self.assertIn("linkedin.com/", url)

    def test_summary(self):
        text = "João Silva\nExperiência em atendimento ao cliente e vendas.\nAtuou 3 anos em loja.\nEmail: a@b.com"
        summary = build_professional_summary(text)
        self.assertIsNotNone(summary)
        self.assertNotIn("@", summary)

    def test_validate_contact(self):
        self.assertEqual(validate_contact("a@b.com", "11999999999"), [])
        warnings = validate_contact(None, None)
        self.assertTrue(any("Email" in w for w in warnings))
        self.assertTrue(any("Telefone" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
