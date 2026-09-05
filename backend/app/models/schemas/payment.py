"""
Payment and subscription Pydantic schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    free = "free"
    gold = "gold"
    platinum = "platinum"


class PlanId(str, Enum):
    gold_monthly = "gold_monthly"
    gold_quarterly = "gold_quarterly"
    platinum_monthly = "platinum_monthly"
    platinum_quarterly = "platinum_quarterly"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateOrderBody(BaseModel):
    """Client requests a Razorpay order for a given plan."""

    plan_id: PlanId


class VerifyPaymentBody(BaseModel):
    """Client posts Razorpay callback data for server-side HMAC verification."""

    razorpay_order_id: str = Field(..., min_length=1)
    razorpay_payment_id: str = Field(..., min_length=1)
    razorpay_signature: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class OrderResponse(BaseModel):
    order_id: str          # rzp order id
    amount: int            # paise
    currency: str
    plan_id: str
    key_id: str            # public Razorpay key (safe to send to client)


class SubscriptionStatusResponse(BaseModel):
    user_id: UUID
    tier: SubscriptionTier
    valid_until: Optional[datetime]
    daily_likes_remaining: Optional[int]
    super_likes_remaining: Optional[int]
    can_see_who_liked: bool


class AdminUserMiniResponse(BaseModel):
    """Minimal user record returned in admin lists."""

    id: UUID
    phone_number: str
    first_name: str
    account_status: str
    subscription_tier: str
    created_at: datetime


class ReportResponse(BaseModel):
    id: UUID
    reporter_id: UUID
    reported_id: UUID
    reason: str
    detail: Optional[str]
    resolved: bool
    created_at: datetime
