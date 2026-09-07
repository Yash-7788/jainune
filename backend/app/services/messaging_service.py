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
import html
import logging
import re
import smtplib
from typing import Any, Optional

import asyncpg
import httpx
from fastapi import HTTPException, status

from app.core.config import settings

log = logging.getLogger(__name__)


def _sanitize_phone(phone: str) -> str:
    raw = str(phone or "").strip()
    if not re.match(r"^\+[1-9]\d{7,14}$", raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number. Expected E.164 format (e.g. +919876543210).",
        )
    return raw


def _sanitize_email(email_addr: str) -> str:
    cleaned = str(email_addr or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recipient email address format.",
        )
    return cleaned


def _mask_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", str(phone or ""))
    if len(cleaned) >= 8:
        return cleaned[:4] + "*" * (len(cleaned) - 8) + cleaned[-4:]
    return "***"


def _mask_email(email_str: str) -> str:
    parts = str(email_str or "").split("@")
    if len(parts) == 2:
        user, domain = parts
        masked = (user[0] + "*" * (len(user) - 1)) if len(user) > 1 else "*"
        return f"{masked}@{domain}"
    return "***"


async def send_sms_otp(phone_number: str, otp: str) -> None:
    """Dispatches 6-digit verification code via MSG91 SMS gateway."""
    phone_clean = _sanitize_phone(phone_number)
    if not re.match(r"^\d{6}$", otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP format.")

    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK SMS] Dispatched OTP %s to %s", otp, _mask_phone(phone_clean))
        return

    mobile = phone_clean.lstrip("+")
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
                log.warning("SMS gateway responded with %s for %s", resp.status_code, _mask_phone(phone_clean))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="SMS gateway temporarily unavailable. Retry shortly.",
                )
    except httpx.RequestError as exc:
        log.warning("SMS gateway connection error for %s: %s", _mask_phone(phone_clean), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS gateway connection timeout.",
        )


async def send_whatsapp_otp(phone_number: str, otp: str) -> None:
    """Dispatches 6-digit verification code via WhatsApp Business gateway."""
    clean_phone = _sanitize_phone(phone_number)
    if not re.match(r"^\d{6}$", otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP format.")

    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK WHATSAPP] Dispatched OTP %s to %s", otp, _mask_phone(clean_phone))
        return

    mobile = clean_phone.lstrip("+")
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
                log.warning("WhatsApp gateway responded with %s for %s; falling back to SMS", resp.status_code, _mask_phone(clean_phone))
                await send_sms_otp(clean_phone, otp)
    except httpx.RequestError as exc:
        log.warning("WhatsApp gateway error for %s (%s); falling back to SMS", _mask_phone(clean_phone), exc)
        await send_sms_otp(clean_phone, otp)


def _send_smtp_email_sync(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    """Synchronous SMTP email delivery with CRLF injection protection."""
    msg = email.message.EmailMessage()
    # Prevent CRLF header injection in email subject
    clean_subject = re.sub(r"[\r\n]+", " ", str(subject or "")).strip()
    msg["Subject"] = clean_subject
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
    """Sends transactional email via SMTP or logs in mock mode with recipient sanitization."""
    clean_to = _sanitize_email(to_email)
    if not settings.smtp_host or settings.debug:
        log.info("[MOCK EMAIL] To: %s | Subject: %s | Text: %s", _mask_email(clean_to), subject, text_body[:80])
        return

    try:
        await asyncio.to_thread(_send_smtp_email_sync, clean_to, subject, html_body, text_body)
    except Exception as exc:
        log.error("Failed to deliver transactional email to %s: %s", _mask_email(clean_to), exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery service temporarily unavailable.",
        )


async def send_email_otp(to_email: str, otp: str) -> None:
    """Renders and delivers secure 6-digit OTP verification email."""
    clean_to = _sanitize_email(to_email)
    if not re.match(r"^\d{6}$", otp):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP format.")

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
    """Dispatches phone OTP via requested channel (sms or whatsapp) with automatic gateway failover."""
    if channel.lower() == "whatsapp":
        await send_whatsapp_otp(phone_number, otp)
    else:
        try:
            await send_sms_otp(phone_number, otp)
        except HTTPException as exc:
            # Automatic failover to WhatsApp on SMS gateway downtime / DLT template congestion
            if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and not settings.debug:
                log.warning("SMS gateway 503 for %s; attempting automatic WhatsApp OTP failover", _mask_phone(phone_number))
                try:
                    await send_whatsapp_otp(phone_number, otp)
                    log.info("WhatsApp failover succeeded for %s", _mask_phone(phone_number))
                    return
                except Exception as fb_err:
                    log.error("WhatsApp OTP fallback failed for %s: %s", _mask_phone(phone_number), fb_err)
            raise exc


# ---------------------------------------------------------------------------
# Promotional & Marketing Messaging System (SMS, WhatsApp, Email)
# ---------------------------------------------------------------------------


async def send_promotional_sms(
    phone_number: str,
    message: str,
    flow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sends promotional SMS via MSG91 Flow / Campaign API with phone and content sanitization."""
    clean_phone = _sanitize_phone(phone_number)
    clean_message = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", str(message or "")).strip()

    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK PROMO SMS] To: %s | Message: %s", _mask_phone(clean_phone), clean_message[:60])
        return {"success": True, "channel": "sms", "mock": True}

    mobile = clean_phone.lstrip("+")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/flow/",
                headers={
                    "authkey": settings.msg91_auth_key,
                    "content-type": "application/json",
                },
                json={
                    "flow_id": flow_id or settings.msg91_promotional_flow_id or settings.msg91_otp_template_id,
                    "sender": "JAINUN",
                    "mobiles": mobile,
                    "message": clean_message,
                },
            )
            return {"success": resp.status_code in (200, 201), "channel": "sms", "status_code": resp.status_code}
    except Exception as exc:
        log.warning("Promotional SMS failed for %s: %s", _mask_phone(clean_phone), exc)
        return {"success": False, "channel": "sms", "error": str(exc)}


async def send_promotional_whatsapp(
    phone_number: str,
    template_name: str,
    parameters: dict[str, str],
    fallback_message: Optional[str] = None,
) -> dict[str, Any]:
    """Dispatches promotional WhatsApp template message with sanitization and SMS fallback."""
    clean_phone = _sanitize_phone(phone_number)
    clean_params = {
        str(k): re.sub(r"[\x00-\x1F\x7F]", " ", str(v or "")).strip()
        for k, v in parameters.items()
    }

    if settings.debug or settings.msg91_auth_key in ("mock", "test", "test_msg91_key", ""):
        log.info("[MOCK PROMO WHATSAPP] To: %s | Template: %s", _mask_phone(clean_phone), template_name)
        return {"success": True, "channel": "whatsapp", "mock": True}

    mobile = clean_phone.lstrip("+")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
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
                        "template_name": template_name,
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": v} for v in clean_params.values()],
                            }
                        ],
                    },
                },
            )
            if resp.status_code in (200, 201):
                return {"success": True, "channel": "whatsapp"}
            log.warning("WhatsApp promotional delivery failed (%s); fallback to SMS", resp.status_code)
    except Exception as exc:
        log.warning("WhatsApp promotional error: %s; fallback to SMS", exc)

    if fallback_message:
        return await send_promotional_sms(clean_phone, fallback_message)
    return {"success": False, "channel": "whatsapp"}


async def send_promotional_email(
    to_email: str,
    subject: str,
    title: str,
    body_text: str,
    offer_badge: Optional[str] = None,
    cta_title: Optional[str] = None,
    cta_url: Optional[str] = None,
) -> bool:
    """Delivers branded promotional / marketing email with strict HTML escaping and URL protocol whitelisting."""
    clean_to = _sanitize_email(to_email)
    safe_title = html.escape(str(title or "").strip())
    safe_body = html.escape(str(body_text or "").strip()).replace("\n", "<br/>")
    safe_badge = html.escape(str(offer_badge or "").strip()) if offer_badge else ""
    safe_cta_title = html.escape(str(cta_title or "Explore Jainune+").strip())

    # Strict URL validation: allow only http:// and https:// (mitigate javascript: / phishing XSS)
    raw_url = str(cta_url or "https://jainune.com").strip()
    if not re.match(r"^https?://[a-zA-Z0-9.-]+", raw_url, re.IGNORECASE):
        raw_url = "https://jainune.com"
    safe_cta_url = html.escape(raw_url, quote=True)

    badge_html = f"""
    <div style="display: inline-block; background-color: #FEF3C7; color: #92400E; font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 9999px; margin-bottom: 16px; border: 1px solid #FCD34D;">
        {safe_badge}
    </div>
    """ if safe_badge else ""

    cta_html = f"""
    <div style="margin: 28px 0; text-align: center;">
        <a href="{safe_cta_url}" style="background-color: #D97706; color: #FFFFFF; font-weight: 600; text-decoration: none; padding: 14px 28px; border-radius: 12px; display: inline-block; font-size: 15px;">
            {safe_cta_title}
        </a>
    </div>
    """

    html_body = f"""<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #FAFAF8; padding: 24px; color: #1C1917; margin: 0;">
    <div style="max-width: 520px; margin: 0 auto; background: #FFFFFF; border-radius: 16px; padding: 32px; border: 1px solid #E7E5E4;">
      <div style="text-align: center; margin-bottom: 24px;">
        <span style="font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: #D97706;">JAINUNE</span>
      </div>
      {badge_html}
      <h2 style="font-size: 22px; font-weight: 700; color: #1C1917; margin: 0 0 16px 0; line-height: 28px;">{safe_title}</h2>
      <p style="font-size: 15px; line-height: 24px; color: #44403C; margin: 0 0 16px 0;">{safe_body}</p>
      {cta_html}
      <hr style="border: none; border-top: 1px solid #F5F5F4; margin: 28px 0;" />
      <p style="font-size: 12px; color: #A8A29E; text-align: center; line-height: 18px; margin: 0;">
        You received this update because you are a valued member of the Jainune community.<br/>
        © 2026 Jainune Inc. • Crafted with Ahimsa & Intentionality
      </p>
    </div>
  </body>
</html>"""

    plain_text = f"Jai Jinendra\n\n{title}\n\n{body_text}\n\n{cta_title or 'Visit'}: {raw_url}\n\nTeam Jainune"
    try:
        await send_email(clean_to, subject, html_body, plain_text)
        return True
    except Exception as exc:
        log.warning("Promotional email delivery failed for %s: %s", _mask_email(clean_to), exc)
        return False


async def broadcast_promotional_campaign(
    pool: asyncpg.Pool,
    campaign_name: str,
    title: str,
    message: str,
    channels: list[str],
    target_segment: str = "free",
    offer_badge: Optional[str] = None,
    cta_url: Optional[str] = None,
    limit: int = 500,
) -> dict[str, Any]:
    """
    Executes broadcast promotional marketing campaign across SMS, WhatsApp, and/or Email.
    Respects user account status and active segments.
    """
    if cta_url:
        from app.core.security import is_safe_public_url
        if not is_safe_public_url(cta_url):
            raise ValueError("Invalid cta_url: internal or loopback addresses forbidden (SSRF protection).")

    where_clause = "u.account_status = 'active'"
    params: list[Any] = []
    if target_segment == "free":
        params.append("free")
        where_clause += f" AND u.subscription_tier = ${len(params)}"
    elif target_segment == "plus":
        where_clause += " AND u.subscription_tier != 'free'"

    # Enforce marketing opt-in consent under DPDP Act 2023 & TRAI regulations
    where_clause += """
        AND EXISTS (
            SELECT 1 FROM consent_records cr
            WHERE cr.user_id = u.id
              AND cr.consent_type = 'marketing'
              AND cr.granted = TRUE
        )
    """

    params.append(limit)
    query = f"""
        SELECT u.id, u.phone_number, u.email, u.first_name
        FROM users u
        WHERE {where_clause}
        ORDER BY u.created_at DESC
        LIMIT ${len(params)}
    """
    async with pool.acquire() as conn:
        users = await conn.fetch(query, *params)

    stats = {
        "campaign": campaign_name,
        "targeted": len(users),
        "sms_sent": 0,
        "whatsapp_sent": 0,
        "email_sent": 0,
        "errors": 0,
    }

    channels_set = set(c.lower() for c in channels)

    for u in users:
        phone = u.get("phone_number")
        email_addr = u.get("email")

        # Email dispatch
        if "email" in channels_set and email_addr:
            try:
                ok = await send_promotional_email(
                    to_email=email_addr,
                    subject=title,
                    title=title,
                    body_text=message,
                    offer_badge=offer_badge or "Jainune Special",
                    cta_title="Unlock Jainune+",
                    cta_url=cta_url or "https://jainune.com/plans",
                )
                if ok:
                    stats["email_sent"] += 1
            except Exception:
                stats["errors"] += 1

        # WhatsApp dispatch
        if "whatsapp" in channels_set and phone:
            try:
                res = await send_promotional_whatsapp(
                    phone_number=phone,
                    template_name="jainune_promotional",
                    parameters={"1": u.get("first_name") or "Friend", "2": message},
                    fallback_message=f"Jai Jinendra! {title}: {message}",
                )
                if res.get("success"):
                    stats["whatsapp_sent"] += 1
            except Exception:
                stats["errors"] += 1

        # SMS dispatch (if not using whatsapp or whatsapp was omitted)
        elif "sms" in channels_set and phone:
            try:
                res = await send_promotional_sms(
                    phone_number=phone,
                    message=f"Jainune: {title}. {message}",
                )
                if res.get("success"):
                    stats["sms_sent"] += 1
            except Exception:
                stats["errors"] += 1

    return stats
