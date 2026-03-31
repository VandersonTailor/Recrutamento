import unittest
from datetime import datetime, timedelta

import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.db import Base
from app.models.communication_event import CommunicationEvent
from app.models.processing_log import ProcessingLog
from app.services.communication_dispatcher import CommunicationDispatcherService
from app.services.communication_sender import NonRetryableSendError


class CommunicationDispatcherTests(unittest.TestCase):
    def test_dispatch_due_sends_only_expired_items(self):
        class _OkSender:
            def send(self, **kwargs):
                return {"provider": "mock", "mode": "real"}

        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        now = datetime.utcnow()

        with Session(engine) as db:
            db.add(
                CommunicationEvent(
                    application_id=1,
                    channel="whatsapp",
                    message_id="t-due-1",
                    event_type="interview_reminder",
                    status="planned",
                    body="msg due",
                    scheduled_for=now - timedelta(minutes=10),
                )
            )
            db.add(
                CommunicationEvent(
                    application_id=1,
                    channel="email",
                    message_id="t-future-1",
                    event_type="message",
                    status="planned",
                    body="msg future",
                    scheduled_for=now + timedelta(hours=1),
                )
            )
            db.commit()

            result = CommunicationDispatcherService(db, sender=_OkSender()).dispatch_due(limit=20)
            self.assertEqual(result["processed"], 1)
            self.assertEqual(result["sent"], 1)
            self.assertEqual(result["failed"], 0)

            events = db.execute(select(CommunicationEvent).order_by(CommunicationEvent.id.asc())).scalars().all()
            self.assertEqual(events[0].status, "sent")
            self.assertEqual(events[1].status, "planned")

            logs = db.execute(select(ProcessingLog)).scalars().all()
            self.assertEqual(len(logs), 1)
            self.assertIn("Dispatched", logs[0].message or "")

    def test_dispatch_retries_then_fails(self):
        class _FailSender:
            def send(self, **kwargs):
                raise RuntimeError("temporary down")

        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        now = datetime.utcnow()
        with Session(engine) as db:
            db.add(
                CommunicationEvent(
                    application_id=1,
                    channel="email",
                    message_id="t-retry-1",
                    event_type="message",
                    status="planned",
                    body="retry me",
                    scheduled_for=now - timedelta(minutes=1),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                    max_attempts=2,
                )
            )
            db.commit()

            svc = CommunicationDispatcherService(db, sender=_FailSender())
            first = svc.dispatch_due(limit=10)
            self.assertEqual(first["retrying"], 1)
            ev = db.execute(select(CommunicationEvent)).scalar_one()
            self.assertEqual(ev.status, "retrying")
            ev.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            db.add(ev)
            db.commit()

            second = svc.dispatch_due(limit=10)
            self.assertEqual(second["failed"], 1)
            ev = db.execute(select(CommunicationEvent)).scalar_one()
            self.assertEqual(ev.status, "failed")

    def test_dispatch_non_retryable_goes_failed(self):
        class _BadSender:
            def send(self, **kwargs):
                raise NonRetryableSendError("invalid destination")

        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(bind=engine)
        now = datetime.utcnow()
        with Session(engine) as db:
            db.add(
                CommunicationEvent(
                    application_id=1,
                    channel="email",
                    message_id="t-bad-1",
                    event_type="message",
                    status="planned",
                    body="bad",
                    scheduled_for=now - timedelta(minutes=1),
                    next_attempt_at=now - timedelta(minutes=1),
                    attempts=0,
                    max_attempts=3,
                )
            )
            db.commit()
            out = CommunicationDispatcherService(db, sender=_BadSender()).dispatch_due(limit=10)
            self.assertEqual(out["failed"], 1)
            ev = db.execute(select(CommunicationEvent)).scalar_one()
            self.assertEqual(ev.status, "failed")


if __name__ == "__main__":
    unittest.main()
