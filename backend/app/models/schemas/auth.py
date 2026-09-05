"""
Authentication Pydantic Schemas:
- Strict input validation and sanitization.
- Injection prevention (SQL, XSS, control characters, null bytes).
- Denial-of-Service / buffer overflow bounds on all tokens.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _sanitize_string(v: str | None, max_len: int = 255) -> str | None:
    if v is None:
        return None
    # Strip null bytes and ASCII control characters (0-31 except standard whitespace)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v.strip())
    # Strip potential HTML script tags
    cleaned = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"[<>]", "", cleaned)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


class OTPRequestBody(BaseModel):
    phone_number: str = Field(..., max_length=16, examples=["+919820098200"])

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^\+91[6-9]\d{9}$", clean):
            raise ValueError("Please provide a valid 10-digit Indian mobile number (+91XXXXXXXXXX).")
        return clean


class OTPVerifyBody(BaseModel):
    phone_number: str = Field(..., max_length=16)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^\+91[6-9]\d{9}$", clean):
            raise ValueError("Please provide a valid Indian mobile number.")
        return clean


class EmailOTPRequestBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    turnstile_token: Optional[str] = Field(None, max_length=2048)

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean):
            raise ValueError("Please provide a valid email address.")
        if any(c in clean for c in ["\x00", "\r", "\n", "<", ">", "'", '"']):
            raise ValueError("Email contains disallowed characters.")
        return clean

    @field_validator("turnstile_token")
    @classmethod
    def sanitize_turnstile(cls, v: Optional[str]) -> Optional[str]:
        return _sanitize_string(v, max_len=2048)


class EmailOTPVerifyBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", clean):
            raise ValueError("Please provide a valid email address.")
        return clean


class GoogleAuthBody(BaseModel):
    id_token: str = Field(..., min_length=10, max_length=4096)
    turnstile_token: Optional[str] = Field(None, max_length=2048)

    @field_validator("id_token")
    @classmethod
    def validate_token_format(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.?[A-Za-z0-9-_+/=]*$", clean):
            raise ValueError("Security token format is invalid.")
        return clean


class AppleAuthBody(BaseModel):
    id_token: str = Field(..., min_length=10, max_length=4096)
    first_name: Optional[str] = Field(None, max_length=64)
    last_name: Optional[str] = Field(None, max_length=64)
    turnstile_token: Optional[str] = Field(None, max_length=2048)

    @field_validator("id_token")
    @classmethod
    def validate_token_format(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.?[A-Za-z0-9-_+/=]*$", clean):
            raise ValueError("Security token format is invalid.")
        return clean

    @field_validator("first_name", "last_name")
    @classmethod
    def sanitize_names(cls, v: Optional[str]) -> Optional[str]:
        return _sanitize_string(v, max_len=64)


class TokenRefreshBody(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=512)

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^[A-Za-z0-9_-]+$", clean):
            raise ValueError("Refresh token format is invalid.")
        return clean


class OTPRequestResponse(BaseModel):
    phone_number: str
    retry_after_seconds: int
    expires_in_seconds: int


class TokenResponse(BaseModel):
    user_id: str
    is_new_user: bool
    onboarding_completed: bool
    access_token: str
    refresh_token: str
    expires_in: int


class AccessTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
