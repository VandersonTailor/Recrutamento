import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.communication_event import CommunicationEvent
from app.services.communication_sender import CommunicationSender, NonRetryableSendError, _normalize_phone_br


class CommunicationSenderTests(unittest.TestCase):
    def test_normalize_phone_br(self):
        self.assertEqual(_normalize_phone_br("(51) 99999-0000"), "5551999990000")
        self.assertEqual(_normalize_phone_br("5551999990000"), "5551999990000")
        self.assertEqual(_normalize_phone_br("+55 (51) 99999-0000"), "5551999990000")

    def test_sender_rejects_email_channel(self):
        sender = CommunicationSender()
        event = CommunicationEvent(
            application_id=1,
            channel="email",
            message_id="sender-test-1",
            event_type="message",
            status="planned",
            body="teste",
        )
        with self.assertRaises(NonRetryableSendError):
            sender.send(event=event, recipient_email="a@b.com", recipient_phone=None)


if __name__ == "__main__":
    unittest.main()
