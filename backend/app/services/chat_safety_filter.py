"""
Roblox-style Smart Chat Safety Filter & Anti-Circumvention Moderation Service.

Enforces:
1. Social media handle & app name blocking (snap, insta, gram, whatsapp, telegram, etc.)
2. Competitor dating app name blocking (tinder, bumble, hinge, shaadi, etc.)
3. Phone numbers & multi-digit contact sequences (10 digits, spaced numbers, written digits)
4. Addresses, street names, flat/house numbers, PIN codes, GPS lat/long coordinates
5. Single-character / single-digit stealth tricking across messages:
   - 1st and 2nd single character messages are allowed.
   - Starting on the 3rd single character message (even if interspersed with normal messages),
     the character is blocked and converted to '#'.
6. Redirection / masking of all detected sensitive words to '#'.
7. Moderation disclaimer generation & subscription gating.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Optional, Tuple
from pydantic import BaseModel

if TYPE_CHECKING:
    import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Compiled Detection Regex Patterns
# ---------------------------------------------------------------------------

# 1. Social Media Apps & ID Keywords
_SOCIAL_APPS = [
    r"s[\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*p(?:[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t)?",
    r"\bsc\b",
    r"i[\s\.\-_]*n[\s\.\-_]*s[\s\.\-_]*t[\s\.\-_]*a(?:[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m)?",
    r"\bgram\b",
    r"\big\b",
    r"w[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*s[\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*p",
    r"\bwa\b",
    r"t[\s\.\-_]*e[\s\.\-_]*l[\s\.\-_]*e(?:[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m)?",
    r"\btg\b",
    r"f[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*e[\s\.\-_]*b[\s\.\-_]*o[\s\.\-_]*o[\s\.\-_]*k",
    r"\bfb\b",
    r"t[\s\.\-_]*w[\s\.\-_]*i[\s\.\-_]*t[\s\.\-_]*t[\s\.\-_]*e[\s\.\-_]*r",
    r"x[\s\.\-_]*\.[\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*m",
    r"d[\s\.\-_]*i[\s\.\-_]*s[\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*r[\s\.\-_]*d",
    r"t[\s\.\-_]*h[\s\.\-_]*r[\s\.\-_]*e[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*s",
    r"s[\s\.\-_]*i[\s\.\-_]*g[\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*l",
    r"w[\s\.\-_]*e[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t",
    r"\b(?:my\s+)?(?:insta|snap|tele|tg|wa|fb|social|handle)\s*(?:id|handle|username)?\s*(?:is|:|=)\b",
    r"\b(?:dm|add|msg|message|ping|text|hit)\s+me\s+(?:on|at)\b",
]
_RE_SOCIAL = re.compile("|".join(f"(?:{p})" for p in _SOCIAL_APPS), re.IGNORECASE)

# 2. Competitor Dating & Matrimony Platforms
_DATING_APPS = [
    r"t[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*d[\s\.\-_]*e[\s\.\-_]*r",
    r"b[\s\.\-_]*u[\s\.\-_]*m[\s\.\-_]*b[\s\.\-_]*l[\s\.\-_]*e",
    r"h[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*g[\s\.\-_]*e",
    r"s[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*i",
    r"j[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*v[\s\.\-_]*a[\s\.\-_]*n[\s\.\-_]*s[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*h[\s\.\-_]*i",
    r"b[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*m[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*r[\s\.\-_]*i[\s\.\-_]*m[\s\.\-_]*o[\s\.\-_]*n[\s\.\-_]*y",
    r"b[\s\.\-_]*e[\s\.\-_]*t[\s\.\-_]*t[\s\.\-_]*e[\s\.\-_]*r[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*l[\s\.\-_]*f",
    r"\baisle\b",
    r"d[\s\.\-_]*i[\s\.\-_]*l[\s\.\-_]*m[\s\.\-_]*i[\s\.\-_]*l",
    r"h[\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*p[\s\.\-_]*n",
    r"o[\s\.\-_]*k[\s\.\-_]*c[\s\.\-_]*u[\s\.\-_]*p[\s\.\-_]*i[\s\.\-_]*d",
    r"\bpure\b",
    r"c[\s\.\-_]*o[\s\.\-_]*f[\s\.\-_]*f[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*m[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*t[\s\.\-_]*s[\s\.\-_]*b[\s\.\-_]*a[\s\.\-_]*g[\s\.\-_]*e[\s\.\-_]*l",
    r"b[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*o[\s\.\-_]*o",
    r"g[\s\.\-_]*r[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*d[\s\.\-_]*r",
    r"q[\s\.\-_]*u[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*k[\s\.\-_]*q[\s\.\-_]*u[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*k",
]
_RE_DATING = re.compile("|".join(f"(?:{p})" for p in _DATING_APPS), re.IGNORECASE)

# 3. Phone Numbers & Numeric Sequences
_PHONE_PATTERNS = [
    # Standard 10-digit Indian phone with optional country code (+91, 91, 0)
    r"(?:\+?91[\s\.\-_]*)?[6-9]\d{9}\b",
    # Spaced / dot / dash separated 10 digits
    r"\b[6-9](?:[\s\.\-_]*\d){9}\b",
    # 7 or more contiguous or spaced digits
    r"\b\d(?:[\s\.\-_]*\d){6,}\b",
    # Written word number patterns (three or more written digits in sequence)
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine)(?:[\s\.\-_]+(?:zero|one|two|three|four|five|six|seven|eight|nine)){2,}\b",
]
_RE_PHONE = re.compile("|".join(f"(?:{p})" for p in _PHONE_PATTERNS), re.IGNORECASE)

# 4. Addresses, Street Names, PIN Codes & GPS Coordinates
_ADDRESS_PATTERNS = [
    # 6-digit Indian PIN code
    r"\b[1-9]\d{5}\b",
    # Lat/Long GPS coordinates: e.g. 19.0760, 72.8777
    r"\b[-+]?\d{1,2}\.\d{3,}\s*[,;\s]\s*[-+]?\d{1,3}\.\d{3,}\b",
    # Flat / House / Plot / Bldg / Apartment number
    r"\b(?:flat|house|plot|bldg|building|apt|apartment|sector|block|room)\s*(?:no|number)?\.?\s*[0-9a-zA-Z\-/]+\b",
    # Street / Road / Marg / Lane / Gali / Nagar / Colony / Chowk names
    r"\b[0-9a-zA-Z\-/]+\s*(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|cross|main|chowk|rasta|bazaar|layout|enclave|vihar|phase)\b",
    r"\b(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|chowk|rasta|bazaar)\s+[0-9a-zA-Z\-/]+\b",
]
_RE_ADDRESS = re.compile("|".join(f"(?:{p})" for p in _ADDRESS_PATTERNS), re.IGNORECASE)


class ModerationResult(BaseModel):
    content: str
    is_moderated: bool
    moderation_type: Optional[str] = None
    moderation_disclaimer: Optional[str] = None
    requires_subscription: bool = False


def _mask_match(match: re.Match) -> str:
    """Replaces matched substring with '#' preserving non-space length."""
    return "#" * len(match.group(0))


async def filter_chat_content(
    content: str,
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    redis: aioredis.Redis,
    is_subscribed: bool = False,
    user_disclaimer_approved: bool = False,
) -> ModerationResult:
    """
    Evaluates message content against chat safety rules:
    - Single-character sequential stealth tracking in Redis (masks 3rd+ single chars).
    - Regex masking for Social IDs, Dating Apps, Phone numbers, and Physical addresses.
    - If user is subscribed and approved disclaimer: allows unmasked exchange.
    - Else: masks all occurrences to '#' and attaches disclaimer.
    """
    if not content:
        return ModerationResult(content="", is_moderated=False)

    trimmed = content.strip()
    detected_types: list[str] = []

    # -------------------------------------------------------------------------
    # 1. Single-character / single-digit stealth tracking (Roblox style)
    # -------------------------------------------------------------------------
    if len(trimmed) == 1:
        single_char_key = f"chat:safety:single_chars:{chat_id}:{user_id}"
        count = await redis.incr(single_char_key)
        if count == 1:
            await redis.expire(single_char_key, 86400 * 30)  # 30-day persistence

        if count >= 3:
            # 3rd single-character message: block and mask to '#'
            return ModerationResult(
                content="#",
                is_moderated=True,
                moderation_type="SINGLE_CHAR_SEQUENCE",
                moderation_disclaimer="Single character sequence detected. Contact information exchange is restricted.",
                requires_subscription=not is_subscribed,
            )
        else:
            # 1st and 2nd single character: allowed without masking or popup
            return ModerationResult(
                content=content,
                is_moderated=False,
            )

    # -------------------------------------------------------------------------
    # 2. Pattern Scans (Social ID, Competitors, Phone, Address)
    # -------------------------------------------------------------------------
    has_social = bool(_RE_SOCIAL.search(content))
    has_dating = bool(_RE_DATING.search(content))
    has_phone = bool(_RE_PHONE.search(content))
    has_address = bool(_RE_ADDRESS.search(content))

    if has_phone:
        detected_types.append("NUMBERS")
    if has_social:
        detected_types.append("SOCIAL_ID")
    if has_dating:
        detected_types.append("DATING_APP")
    if has_address:
        detected_types.append("ADDRESS")

    if not detected_types:
        return ModerationResult(content=content, is_moderated=False)

    # Determine primary detection category
    primary_type = detected_types[0]

    # Generate disclaimer
    if primary_type == "NUMBERS":
        disclaimer = "You are trying to exchange phone numbers. Exchange at your own risk and only if you trust."
    elif primary_type == "SOCIAL_ID":
        disclaimer = "You are trying to exchange social media handles or IDs. Exchange at your own risk and only if you trust."
    elif primary_type == "DATING_APP":
        disclaimer = "Referencing outside dating platforms is restricted. Exchange at your own risk and only if you trust."
    else:
        disclaimer = "You are trying to exchange physical address or GPS coordinates. Exchange at your own risk and only if you trust."

    # -------------------------------------------------------------------------
    # 3. Subscription & Approval Gate
    # -------------------------------------------------------------------------
    # If user has active subscription AND explicitly approved disclaimer:
    if is_subscribed and user_disclaimer_approved:
        return ModerationResult(
            content=content,
            is_moderated=False,
            moderation_type=primary_type,
            moderation_disclaimer=disclaimer,
            requires_subscription=False,
        )

    # Otherwise: Mask all detected sensitive words to '#'
    masked_content = content
    masked_content = _RE_PHONE.sub(_mask_match, masked_content)
    masked_content = _RE_SOCIAL.sub(_mask_match, masked_content)
    masked_content = _RE_DATING.sub(_mask_match, masked_content)
    masked_content = _RE_ADDRESS.sub(_mask_match, masked_content)

    return ModerationResult(
        content=masked_content,
        is_moderated=True,
        moderation_type=primary_type,
        moderation_disclaimer=disclaimer,
        requires_subscription=not is_subscribed,
    )
