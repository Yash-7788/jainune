"""
Non-Technical, User-Friendly Error Management:
Transforms technical exceptions, HTTP status codes, validation errors,
and database failures into clean, non-technical, empathetic user messages.
No status codes or internal stack traces are ever displayed to end users.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

log = logging.getLogger(__name__)

# Base human-friendly copy for HTTP categories
DEFAULT_USER_MESSAGES: dict[int, tuple[str, str]] = {
    400: (
        "INVALID_INPUT",
        "Some details seem incomplete or incorrect. Please review and try again.",
    ),
    401: (
        "SESSION_EXPIRED",
        "Your session has ended. Please sign in again to continue.",
    ),
    403: (
        "ACCESS_RESTRICTED",
        "This action cannot be completed right now. Please reach out to support if you need assistance.",
    ),
    404: (
        "NOT_FOUND",
        "The profile, match, or screen you are looking for is no longer available.",
    ),
    409: (
        "ALREADY_EXISTS",
        "This information has already been registered or updated.",
    ),
    422: (
        "VALIDATION_ERROR",
        "Please check the entered information to ensure all fields are filled properly.",
    ),
    429: (
        "TOO_MANY_REQUESTS",
        "You are moving a bit fast! Please take a quick breather and try again in a moment.",
    ),
    500: (
        "TEMPORARY_ERROR",
        "We hit a snag on our side. Our team has been notified; please check back shortly.",
    ),
    502: (
        "CONNECTION_PROBLEM",
        "We are having trouble reaching our servers. Please check your internet connection.",
    ),
    503: (
        "MAINTENANCE",
        "Jainune is undergoing brief scheduled maintenance. Please check back in a few minutes.",
    ),
    504: (
        "TIMEOUT",
        "The request took longer than expected. Please verify your connection and try again.",
    ),
}

# Contextual phrases mapped to empathetic explanations
KEYWORD_MAPPINGS: list[tuple[list[str], str, str]] = [
    (
        ["disposable", "burner", "temporary email"],
        "DISPOSABLE_EMAIL_BLOCKED",
        "Please use your personal or work email. Temporary email addresses are not supported.",
    ),
    (
        ["automated or unsupported client", "turnstile", "bot integrity", "security verification challenge"],
        "CLIENT_INTEGRITY_FAILED",
        "Security check could not be verified. Please make sure you are using the official Jainune app.",
    ),
    (
        ["rate limit", "sliding window", "too many otp"],
        "OTP_RATE_LIMIT",
        "Too many verification attempts. Please wait a couple of minutes before requesting another code.",
    ),
    (
        ["invalid or expired otp", "incorrect otp", "otp expired"],
        "INVALID_OTP",
        "The verification code entered is incorrect or has expired. Please request a new code.",
    ),
    (
        ["user account has been deleted", "account has been deleted"],
        "ACCOUNT_DELETED",
        "This account is no longer active.",
    ),
    (
        ["permanently banned", "account_status == 'banned'"],
        "ACCOUNT_BANNED",
        "This account has been closed in accordance with our community guidelines.",
    ),
    (
        ["temporarily suspended"],
        "ACCOUNT_SUSPENDED",
        "Your account is temporarily suspended. Please contact support for assistance.",
    ),
    (
        ["daily like limit", "daily connects", "quota exceeded"],
        "DAILY_LIMIT_REACHED",
        "You've used all your complimentary connects for today. Upgrade your plan or check back tomorrow!",
    ),
    (
        ["super connect", "insufficient credits"],
        "INSUFFICIENT_CREDITS",
        "You need additional Super Connect credits to send this note.",
    ),
    (
        ["not matched", "blocked", "cannot send message"],
        "CHAT_NOT_ALLOWED",
        "You cannot send messages in this conversation.",
    ),
]


def resolve_friendly_error(status_code: int, raw_detail: str) -> tuple[str, str]:
    """
    Transforms any technical error message or status code into a human-friendly
    (error_code, user_friendly_message) pair.
    """
    detail_lower = str(raw_detail).lower()

    # Check contextual keyword triggers first
    for keywords, code, friendly_msg in KEYWORD_MAPPINGS:
        if any(kw in detail_lower for kw in keywords):
            return code, friendly_msg

    # Fall back to status code dictionary
    if status_code in DEFAULT_USER_MESSAGES:
        return DEFAULT_USER_MESSAGES[status_code]

    # Universal fallback for unknown / unhandled codes
    return (
        "UNEXPECTED_ERROR",
        "Something unexpected happened. Please check your internet connection and try again.",
    )


def create_error_envelope(
    status_code: int,
    error_code: str,
    user_message: str,
    raw_details: Any = None,
) -> dict:
    """Standardizes every error response without revealing raw status codes or tech jargon."""
    return {
        "success": False,
        "data": None,
        "error": {
            "code": error_code,
            "message": user_message,
            "user_message": user_message,
            "details": raw_details if settings.debug else [],
        },
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:16]}",
        },
    }


# ── Global FastAPI Exception Handlers ─────────────────────────────────────────

async def http_exception_handler(request: Request, exc: HTTPException | StarletteHTTPException) -> JSONResponse:
    raw_detail = str(exc.detail) if hasattr(exc, "detail") else str(exc)
    code, friendly_msg = resolve_friendly_error(exc.status_code, raw_detail)
    envelope = create_error_envelope(exc.status_code, code, friendly_msg, raw_details=[raw_detail])
    return JSONResponse(status_code=exc.status_code, content=envelope)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    code, friendly_msg = resolve_friendly_error(422, "validation error")
    envelope = create_error_envelope(422, code, friendly_msg, raw_details=exc.errors())
    return JSONResponse(status_code=422, content=envelope)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception(f"Unhandled server error on {request.url.path}: {exc}")
    code, friendly_msg = resolve_friendly_error(500, str(exc))
    envelope = create_error_envelope(500, code, friendly_msg, raw_details=[str(exc)])
    return JSONResponse(status_code=500, content=envelope)
