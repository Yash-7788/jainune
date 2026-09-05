"""
Non-Technical, End-User Friendly & Humorous Error Management:
Transforms technical exceptions, HTTP status codes, validation errors,
and server failures into warm, humorous, empathetic dating-app copy.
Zero status codes or raw stack traces are ever exposed to the user.
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

# Base humorous & empathetic copy for HTTP categories
DEFAULT_USER_MESSAGES: dict[int, tuple[str, str, str]] = {
    400: (
        "INVALID_INPUT",
        "Typo Alert! 🧐",
        "Looks like a little slip of the thumb! Check what you entered and give it another spin.",
    ),
    401: (
        "SESSION_EXPIRED",
        "Time Flies When Having Fun! ⏳",
        "Your session took a little beauty sleep. Please sign in again so you don't miss any new smiles!",
    ),
    403: (
        "ACCESS_RESTRICTED",
        "Hold Your Horses! 🛑",
        "We couldn't verify this action right now. Let's keep things safe and authentic—reach out to support if you're stuck.",
    ),
    404: (
        "NOT_FOUND",
        "Poof! Gone Like Magic 💨",
        "The profile, conversation, or page you are searching for did a disappearing act! It might have moved on.",
    ),
    409: (
        "ALREADY_EXISTS",
        "Déjà Vu! 👥",
        "This information has already found a home with us. Try signing in or using another account.",
    ),
    422: (
        "VALIDATION_ERROR",
        "Almost at the Finish Line! ✍️",
        "A few blanks need your touch. Complete the highlighted fields so we can get your journey rolling!",
    ),
    429: (
        "TOO_MANY_REQUESTS",
        "Whoa, Speed Racer! 🏎️💨",
        "You're tapping faster than Cupid shoots arrows! Take a quick 30-second chai break ☕ and try again.",
    ),
    500: (
        "TEMPORARY_ERROR",
        "Our Servers Need a Chai Break ☕",
        "Our servers got a bit starry-eyed and tripped over a wire! 🙈 Our engineers are untangling it right now. Hang tight!",
    ),
    502: (
        "CONNECTION_PROBLEM",
        "Lost in the Cloud Clouds? ☁️",
        "Even true love needs strong Wi-Fi! We're having trouble catching your signal. Check your connection and retry.",
    ),
    503: (
        "MAINTENANCE",
        "Polishing the Matchmaking Mirrors ✨",
        "We're doing a quick tune-up to keep your experience smooth as silk. We'll be right back!",
    ),
    504: (
        "TIMEOUT",
        "Taking the Scenic Route 🐢",
        "The server took a little too long admiring the scenery. Give it another tap to reconnect!",
    ),
}

# Contextual phrases mapped to witty explanations
KEYWORD_MAPPINGS: list[tuple[list[str], str, str, str]] = [
    (
        ["disposable", "burner", "temporary email"],
        "DISPOSABLE_EMAIL_BLOCKED",
        "Real Connections Only! 💌",
        "We love authentic vibes! Please use your personal or work email—burner inboxes break Cupid's heart.",
    ),
    (
        ["automated or unsupported client", "turnstile", "bot integrity", "security verification challenge"],
        "CLIENT_INTEGRITY_FAILED",
        "Are You a Robot? 🤖",
        "Beep boop! Our anti-bot radar went off. Please make sure you're using the official Jainune mobile app.",
    ),
    (
        ["rate limit", "sliding window", "too many otp"],
        "OTP_RATE_LIMIT",
        "Patience, Young Cupid! 🏹",
        "Too many codes requested in a flash. Grab a sip of water and try again in a couple of minutes.",
    ),
    (
        ["invalid or expired otp", "incorrect otp", "otp expired", "invalid verification code"],
        "INVALID_OTP",
        "Vanished Like the Last Samosa! 🥟",
        "That 6-digit code doesn't match or has expired. Request a fresh code and we'll send it right over!",
    ),
    (
        ["user account has been deleted", "account has been deleted"],
        "ACCOUNT_DELETED",
        "New Chapters Await 📖",
        "This account has completed its journey and is no longer active. Create a fresh profile to start anew!",
    ),
    (
        ["permanently banned", "account_status == 'banned'"],
        "ACCOUNT_BANNED",
        "Good Vibes Only 🕊️",
        "This account has been closed to protect our community's trust and respect.",
    ),
    (
        ["temporarily suspended"],
        "ACCOUNT_SUSPENDED",
        "Taking a Little Timeout ⏸️",
        "Your account is taking a temporary pause. Reach out to our friendly support team for help.",
    ),
    (
        ["daily like limit", "daily connects", "quota exceeded"],
        "DAILY_LIMIT_REACHED",
        "Cupid's Quiver is Empty for Today! 🏹",
        "You've shared so much love today! You've used all your daily complimentary connects. Recharge with Gold or check back tomorrow!",
    ),
    (
        ["super connect", "insufficient credits"],
        "INSUFFICIENT_CREDITS",
        "Out of Super Sparks! ✨",
        "You need a Super Connect credit to send this note directly. Top up your coin wallet in the Arcade!",
    ),
    (
        ["not matched", "blocked", "cannot send message"],
        "CHAT_NOT_ALLOWED",
        "Silence is Golden 🤫",
        "This conversation is taking a pause or is no longer active.",
    ),
    (
        ["sms gateway", "sms temporarily unavailable"],
        "SMS_GATEWAY_BUSY",
        "The Carrier Pigeon is Resting 🕊️",
        "Our SMS carrier is catching its breath! Give it 60 seconds and request your code again.",
    ),
]


def resolve_friendly_error(status_code: int, raw_detail: str) -> tuple[str, str, str]:
    """
    Transforms any technical error message or status code into a human-friendly,
    humorous (error_code, title, user_friendly_message) triplet.
    """
    detail_lower = str(raw_detail).lower()

    # Check contextual keyword triggers first
    for keywords, code, title, friendly_msg in KEYWORD_MAPPINGS:
        if any(kw in detail_lower for kw in keywords):
            return code, title, friendly_msg

    # Fall back to status code dictionary
    if status_code in DEFAULT_USER_MESSAGES:
        return DEFAULT_USER_MESSAGES[status_code]

    # Universal fallback for unknown / unhandled codes
    return (
        "UNEXPECTED_ERROR",
        "Little Bump on the Road 🛣️",
        "Something unexpected happened. Check your internet connection and give it another shot!",
    )


def create_error_envelope(
    status_code: int,
    error_code: str,
    title: str,
    user_message: str,
    raw_details: Any = None,
) -> dict:
    """Standardizes every error response with zero status codes or technical jargon."""
    return {
        "success": False,
        "data": None,
        "error": {
            "code": error_code,
            "title": title,
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
    code, title, friendly_msg = resolve_friendly_error(exc.status_code, raw_detail)
    envelope = create_error_envelope(exc.status_code, code, title, friendly_msg, raw_details=[raw_detail])
    return JSONResponse(status_code=exc.status_code, content=envelope)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    code, title, friendly_msg = resolve_friendly_error(422, "validation error")
    envelope = create_error_envelope(422, code, title, friendly_msg, raw_details=exc.errors())
    return JSONResponse(status_code=422, content=envelope)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception(f"Unhandled server error on {request.url.path}: {exc}")
    code, title, friendly_msg = resolve_friendly_error(500, str(exc))
    envelope = create_error_envelope(500, code, title, friendly_msg, raw_details=[str(exc)])
    return JSONResponse(status_code=500, content=envelope)
