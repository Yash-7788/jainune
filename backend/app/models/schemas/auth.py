import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class OTPRequestBody(BaseModel):
    phone_number: str = Field(..., examples=["+919820098200"])

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^\+91[6-9]\d{9}$", v):
            raise ValueError("phone_number must be a valid Indian mobile number (+91XXXXXXXXXX)")
        return v


class OTPVerifyBody(BaseModel):
    phone_number: str
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class TokenRefreshBody(BaseModel):
    refresh_token: str = Field(..., min_length=10)


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


class EmailOTPRequestBody(BaseModel):
    email: str = Field(..., max_length=255)
    turnstile_token: str | None = None


class EmailOTPVerifyBody(BaseModel):
    email: str = Field(..., max_length=255)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class GoogleAuthBody(BaseModel):
    id_token: str = Field(..., min_length=10)
    turnstile_token: str | None = None


class AppleAuthBody(BaseModel):
    id_token: str = Field(..., min_length=10)
    first_name: str | None = Field(None, max_length=64)
    last_name: str | None = Field(None, max_length=64)
    turnstile_token: str | None = None

