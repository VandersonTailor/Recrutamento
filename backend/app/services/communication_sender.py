from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
import re
from urllib import error as urlerror
from urllib import request as urlrequest

from app.core.config import get_settings
from app.models.communication_event import CommunicationEvent


class NonRetryableSendError(RuntimeError):
    pass


class CommunicationSender:
    def send(
        self,
        *,
        event: CommunicationEvent,
        recipient_email: str | None,
        recipient_phone: str | None,
    ) -> dict:
        channel = str(event.channel or "").strip().lower()
        if channel == "email":
            raise NonRetryableSendError("Canal email desabilitado. Use apenas WhatsApp via WPPConnect.")
        if channel == "whatsapp":
            return self._send_whatsapp(event=event, recipient_phone=recipient_phone)
        raise NonRetryableSendError(f"Canal não suportado: {channel}")

    def _send_email(self, *, event: CommunicationEvent, recipient_email: str | None) -> dict:
        settings = get_settings()
        if not recipient_email:
            raise NonRetryableSendError("Email do destinatário ausente para envio.")

        if not settings.smtp_enabled:
            return {"mode": "simulated", "provider": "smtp", "recipient": recipient_email}

        if not settings.smtp_host or not settings.smtp_from_email:
            raise NonRetryableSendError("Configuração SMTP incompleta (host/from).")

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = recipient_email
        message["Subject"] = event.subject or "Atualização de recrutamento"
        message.set_content(event.body or "")

        timeout = max(5, int(settings.smtp_timeout_seconds or 20))
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, int(settings.smtp_port), timeout=timeout) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=timeout) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)

        return {"mode": "real", "provider": "smtp", "recipient": recipient_email}

    def _send_whatsapp(self, *, event: CommunicationEvent, recipient_phone: str | None) -> dict:
        settings = get_settings()
        if not recipient_phone:
            raise NonRetryableSendError("Telefone do destinatário ausente para envio WhatsApp.")

        phone = _normalize_phone_br(recipient_phone)
        if not phone:
            raise NonRetryableSendError("Telefone inválido para envio WhatsApp.")

        if not settings.wppconnect_enabled:
            return {"mode": "simulated", "provider": "wppconnect", "recipient": phone}

        if not settings.wppconnect_base_url or not settings.wppconnect_instance:
            raise NonRetryableSendError("Configuração WPPConnect incompleta (base_url/instance).")

        send_path = (settings.wppconnect_send_path or "/api/{instance}/send-message").format(
            instance=settings.wppconnect_instance
        )
        base = settings.wppconnect_base_url.rstrip("/")
        path = send_path if send_path.startswith("/") else f"/{send_path}"
        endpoint = f"{base}{path}"

        payload = {
            "phone": phone,
            "message": event.body or "",
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urlrequest.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if settings.wppconnect_auth_token:
            req.add_header("Authorization", f"Bearer {settings.wppconnect_auth_token}")
        if settings.wppconnect_secret_key:
            req.add_header("secretkey", settings.wppconnect_secret_key)

        timeout = max(5, int(settings.wppconnect_timeout_seconds or 20))
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                status = int(getattr(resp, "status", 0) or 0)
                content = resp.read().decode("utf-8", errors="ignore")
        except urlerror.HTTPError as exc:  # pragma: no cover
            if 400 <= int(exc.code) < 500:
                raise NonRetryableSendError(f"WPPConnect rejeitou requisição ({exc.code}).") from exc
            raise RuntimeError(f"Falha no WPPConnect ({exc.code}).") from exc
        except urlerror.URLError as exc:  # pragma: no cover
            raise RuntimeError("Falha de conectividade no WPPConnect.") from exc

        if status and status >= 500:
            raise RuntimeError(f"WPPConnect indisponível ({status}).")
        if status and status >= 400:
            raise NonRetryableSendError(f"WPPConnect rejeitou envio ({status}).")
        return {"mode": "real", "provider": "wppconnect", "recipient": phone, "endpoint": endpoint, "response": content[:2000]}


def _normalize_phone_br(phone: str) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) in (10, 11):
        return f"55{digits}"
    if len(digits) > 13:
        return digits[-13:]
    return digits
