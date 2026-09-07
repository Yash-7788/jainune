"""
Unified Messaging Service:
- SMS dispatch via MSG91 OTP API
- WhatsApp dispatch via MSG91 WhatsApp API / Meta Cloud API
- Email dispatch via SMTP / SES with branded HTML templates
- Resilient failover and defensive timeout handling
"""

from __future__ import annotations

import asyncio
import email.message
import logging
import smtplib
from typing import Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

log = logging.getLogger(__name__)


def _mask_phone(phone: str) -> str:
    if len(phone) >= 8:
        return phone[:4] + "*" * (len(phone) - 8) + phone[-4:]
    return "***"


def _mask_email(email_str: str) -> str:
    parts = email_str.split("@")
    if len(parts) == 2:
        user, domain = parts
        masked = (user[0] + "*" * (len(user) - 1)) if len(user) > 1 else "*"
        return f"{masked}@{domain}"
    return "***"


async def send_sms_otp(phone_number: str, otp: str) -> None:
    """Dispatches 6-digit verification code via MSG91 SMS gateway."""
    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK SMS] Dispatched OTP %s to %s", otp, _mask_phone(phone_number))
        return

    mobile = phone_number.lstrip("+")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/otp",
                params={
                    "authkey": settings.msg91_auth_key,
                    "template_id": settings.msg91_otp_template_id,
                    "mobile": mobile,
                    "otp": otp,
                },
            )
            if resp.status_code not in (200, 201):
                log.warning("SMS gateway responded with %s for %s", resp.status_code, _mask_phone(phone_number))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS gateway temporarily unavailable. Retry shortly.",
                )
    except httpx.RequestError as exc:
        log.warning("SMS gateway connection error for %s: %s", _mask_phone(phone_number), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS gateway connection timeout.",
        )


async def send_whatsapp_otp(phone_number: str, otp: str) -> None:
    """Dispatches 6-digit verification code via WhatsApp Business gateway."""
    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK WHATSAPP] Dispatched OTP %s to %s", otp, _mask_phone(phone_number))
        return

    mobile = phone_number.lstrip("+")
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/",
                headers={
                    "authkey": settings.msg91_auth_key,
                    "Content-Type": "application/json",
                },
                json={
                    "integrated_number": mobile,
                    "content_type": "template",
                    "payload": {
                        "template_id": settings.msg91_whatsapp_template_id,
                        "variables": [otp],
                    },
                },
            )
            if resp.status_code not in (200, 201):
                log.warning("WhatsApp gateway responded with %s for %s; falling back to SMS", resp.status_code, _mask_phone(phone_number))
                await send_sms_otp(phone_number, otp)
    except httpx.RequestError as exc:
        log.warning("WhatsApp gateway error for %s (%s); falling back to SMS", _mask_phone(phone_number), exc)
        await send_sms_otp(phone_number, otp)


def _send_smtp_email_sync(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    """Synchronous SMTP email delivery."""
    msg = email.message.EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    """Sends transactional email via SMTP or logs in mock mode."""
    if not settings.smtp_host or settings.debug:
        log.info("[MOCK EMAIL] To: %s | Subject: %s | Text: %s", _mask_email(to_email), subject, text_body[:80])
        return

    try:
        await asyncio.to_thread(_send_smtp_email_sync, to_email, subject, html_body, text_body)
    except Exception as exc:
        log.error("Failed to deliver transactional email to %s: %s", _mask_email(to_email), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery service temporarily unavailable.",
        )


async def send_email_otp(to_email: str, otp: str) -> None:
    """Renders and delivers secure 6-digit OTP verification email."""
    subject = f"{otp} is your Jainune verification code"
    text_body = f"Welcome to Jainune.\n\nYour verification code is: {otp}\n\nThis code expires in 10 minutes. Do not share this code with anyone.\n\nJai Jinendra,\nTeam Jainune"
    html_body = f"""
    <!DOCTYPE html>
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #FAFAF8; padding: 24px; color: #1C1917;">
        <div style="max-width: 480px; margin: 0 auto; background: #FFFFFF; border-radius: 16px; padding: 32px; border: 1px solid #E7E5E4;">
          <h2 style="color: #D97706; margin-top: 0;">Jai Jinendra 🙏</h2>
          <p style="font-size: 16px; line-height: 24px;">Your single-use Jainune verification code is:</p>
          <div style="background: #FEF3C7; border: 1px solid #FCD34D; border-radius: 12px; padding: 16px; text-align: center; margin: 24px 0;">
            <span style="font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #92400E;">{otp}</span>
          </div>
          <p style="font-size: 14px; color: #78716C; line-height: 20px;">
            This code expires in 10 minutes. If you did not request this verification, please safely disregard this email.
          </p>
          <hr style="border: none; border-top: 1px solid #F5F5F4; margin: 24px 0;" />
          <p style="font-size: 12px; color: #A8A29E; text-align: center; margin-bottom: 0;">
            © 2026 Jainune Inc. • Crafted with Ahimsa & Intentionality
          </p>
        </div>
      </body>
    </html>
    """
    await send_email(to_email, subject, html_body, text_body)


async def dispatch_phone_otp(phone_number: str, otp: str, channel: str = "sms") -> None:
    """Dispatches phone OTP via requested channel (sms or whatsapp)."""
    if channel.lower() == "whatsapp":
        await send_whatsapp_otp(phone_number, otp)
    else:
        await send_sms_otp(phone_number, otp)
