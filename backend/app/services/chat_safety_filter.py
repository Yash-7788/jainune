"""
Roblox-style Smart Chat Safety Filter & Anti-Circumvention Moderation Service.

Enforces:
1. Social media handle & app name blocking (snap, insta, gram, whatsapp, telegram, etc.)
2. Competitor dating app name blocking (tinder, bumble, hinge, shaadi, etc.)
3. Phone numbers & multi-digit contact sequences (10 digits, spaced numbers, written digits)
4. Addresses, street names, flat/house numbers, PIN codes, GPS lat/long coordinates
5. Single-character / single-digit stealth tracking across messages:
   - 1st and 2nd single character messages are allowed.
   - Starting on the 3rd single character message (even if interspersed with normal messages),
     the character is blocked and converted to '#'.
6. Redirection / masking of all detected sensitive words to '#'.
7. Moderation disclaimer generation & subscription gating.
8. Zero-width character & unicode homoglyph normalization.
9. Balanced number word detection (series of >= 4-5 words or preceded by 'call/ph').
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import TYPE_CHECKING, Optional
from pydantic import BaseModel

if TYPE_CHECKING:
    import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Text Normalization for Evasion Resistance
# ---------------------------------------------------------------------------

_HOMOGLYPH_MAP = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X",
    "@": "a", "$": "s",
}


def normalize_text_for_moderation(text: str) -> str:
    """Strips zero-width characters and normalizes homoglyphs without corrupting digits."""
    # 1. Strip invisible / zero-width characters
    cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad\u2060]", "", text)
    # 2. Normalize unicode (NFKD)
    cleaned = unicodedata.normalize("NFKD", cleaned)
    # 3. Translate homoglyphs and symbol substitutions
    for k, v in _HOMOGLYPH_MAP.items():
        if k in cleaned:
            cleaned = cleaned.replace(k, v)
    return cleaned


# ---------------------------------------------------------------------------
# Compiled Detection Regex Patterns
# ---------------------------------------------------------------------------

# 1. Social Media Apps & ID Keywords (including leetspeak 1nsta, 5nap)
_SOCIAL_APPS = [
    r"\b[s5][\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*p(?:[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t)?\b",
    r"\bsc\b",
    r"\b[i1!][\s\.\-_]*n[\s\.\-_]*[s5][\s\.\-_]*t[\s\.\-_]*a(?:[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m)?\b",
    r"\bgram\b",
    r"\big\b",
    r"\bw[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*[s5][\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*p\b",
    r"\bwa\b",
    r"\bt[\s\.\-_]*e[\s\.\-_]*l[\s\.\-_]*e(?:[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m)?\b",
    r"\btg\b",
    r"\bf[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*e[\s\.\-_]*b[\s\.\-_]*o[\s\.\-_]*o[\s\.\-_]*k\b",
    r"\bfb\b",
    r"\bt[\s\.\-_]*w[\s\.\-_]*i[\s\.\-_]*t[\s\.\-_]*t[\s\.\-_]*e[\s\.\-_]*r\b",
    r"\bx[\s\.\-_]*\.[\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*m\b",
    r"\bd[\s\.\-_]*i[\s\.\-_]*[s5][\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*r[\s\.\-_]*d\b",
    r"\bt[\s\.\-_]*h[\s\.\-_]*r[\s\.\-_]*e[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*[s5]\b",
    r"\b[s5][\s\.\-_]*i[\s\.\-_]*g[\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*l\b",
    r"\bw[\s\.\-_]*e[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t\b",
    r"\b(?:my\s+)?(?:insta|snap|tele|tg|wa|fb|social|handle)\s*(?:id|handle|username)?\s*(?:is|:|=)\b",
    r"\b(?:dm|add|msg|message|ping|text|hit)\s+me\s+(?:on|at)\b",
]
_RE_SOCIAL = re.compile("|".join(f"(?:{p})" for p in _SOCIAL_APPS), re.IGNORECASE)

# 2. Competitor Dating & Matrimony Platforms
_DATING_APPS = [
    r"\bt[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*d[\s\.\-_]*e[\s\.\-_]*r\b",
    r"\bb[\s\.\-_]*u[\s\.\-_]*m[\s\.\-_]*b[\s\.\-_]*l[\s\.\-_]*e\b",
    r"\bh[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*g[\s\.\-_]*e\b",
    r"\b[s5][\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*i\b",
    r"\bj[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*v[\s\.\-_]*a[\s\.\-_]*n[\s\.\-_]*[s5][\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*h[\s\.\-_]*i\b",
    r"\bb[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*m[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*r[\s\.\-_]*i[\s\.\-_]*m[\s\.\-_]*o[\s\.\-_]*n[\s\.\-_]*y\b",
    r"\bb[\s\.\-_]*e[\s\.\-_]*t[\s\.\-_]*t[\s\.\-_]*e[\s\.\-_]*r[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*l[\s\.\-_]*f\b",
    r"\baisle\b",
    r"\bd[\s\.\-_]*i[\s\.\-_]*l[\s\.\-_]*m[\s\.\-_]*i[\s\.\-_]*l\b",
    r"\bh[\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*p[\s\.\-_]*n\b",
    r"\bo[\s\.\-_]*k[\s\.\-_]*c[\s\.\-_]*u[\s\.\-_]*p[\s\.\-_]*i[\s\.\-_]*d\b",
    r"\bpure\b",
    r"\bc[\s\.\-_]*o[\s\.\-_]*f[\s\.\-_]*f[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*m[\s\.\-_]*e[\s\.\-_]*e[\s\.\-_]*t[\s\.\-_]*[s5][\s\.\-_]*b[\s\.\-_]*a[\s\.\-_]*g[\s\.\-_]*e[\s\.\-_]*l\b",
    r"\bb[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*o[\s\.\-_]*o\b",
    r"\bg[\s\.\-_]*r[\s\.\-_]*i[\s\.\-_]*n[\s\.\-_]*d[\s\.\-_]*r\b",
    r"\bq[\s\.\-_]*u[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*k[\s\.\-_]*q[\s\.\-_]*u[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*k\b",
]
_RE_DATING = re.compile("|".join(f"(?:{p})" for p in _DATING_APPS), re.IGNORECASE)

# 3. Phone Numbers & Numeric Sequences
_PHONE_PATTERNS = [
    # Standard 10-digit Indian phone with optional country code (+91, 91, 0)
    r"(?:\+?91[\s\.\-_]*)?[6-9](?:[\s\.\-_]*\d){9}\b",
    # (987) 654-3210 style
    r"\(\d{3}\)[\s\.\-_]*\d{3}[\s\.\-_]*\d{4}\b",
    # 7 or more contiguous or spaced digits
    r"\b\d(?:[\s\.\-_]*\d){6,}\b",
    # Series of 4 or more word digits: "nine eight seven six five"
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine)(?:[\s\.\-_,]+(?:zero|one|two|three|four|five|six|seven|eight|nine)){3,}\b",
    # 3 or more word digits if preceded by call / phone / number / contact
    r"\b(?:call|phone|ph|num|number|dial|reach|contact)\s+(?:me\s+)?(?:at\s+|on\s+)?(?:zero|one|two|three|four|five|six|seven|eight|nine)(?:[\s\.\-_,]+(?:zero|one|two|three|four|five|six|seven|eight|nine)){2,}\b",
]
_RE_PHONE = re.compile("|".join(f"(?:{p})" for p in _PHONE_PATTERNS), re.IGNORECASE)

# 4. Addresses, Street Names, PIN Codes & GPS Coordinates
_ADDRESS_PATTERNS = [
    # 6-digit Indian PIN code (with optional single space/dash e.g. 400 001)
    r"\b[1-9]\d{2}[\s\.\-_]?\d{3}\b",
    # Lat/Long GPS coordinates: e.g. 19.0760, 72.8777
    r"\b[-+]?\d{1,2}\.\d{3,}\s*[,;\s]\s*[-+]?\d{1,3}\.\d{3,}\b",
    # Flat / House / Plot / Bldg / Apartment number
    r"\b(?:flat|house|plot|bldg|building|apt|apartment|sector|block|room)\s*(?:no|number)?\.?\s*[0-9a-zA-Z\-/]+\b",
    # Specific street/road naming excluding common conversational stop words
    r"\b(?!(?:the|this|that|my|our|any|a|an|at|by|from|near|for|off|on|of|in|to|with|and|or|is|was|were|one|good|bad|big|small|wide|long)\b)[a-zA-Z0-9\-/]{2,}\s+(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|chowk|rasta|bazaar|enclave|vihar|layout)\b",
    r"\b(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|chowk|rasta|bazaar)\s+(?:(?:no|number)\.?\s*)?\d+[a-zA-Z]?\b",
    r"\b(?:sector|block|phase|pocket)\s+[a-zA-Z0-9\-/]+\b",
]
_RE_ADDRESS = re.compile("|".join(f"(?:{p})" for p in _ADDRESS_PATTERNS), re.IGNORECASE)


class ModerationResult(BaseModel):
    content: str
    is_moderated: bool
    moderation_type: Optional[str] = None
    moderation_disclaimer: Optional[str] = None
    requires_subscription: bool = False


def _mask_match(match: re.Match) -> str:
    """Replaces matched substring with '#' preserving length."""
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

    # Normalized text for pattern matching
    normalized = normalize_text_for_moderation(content)

    # -------------------------------------------------------------------------
    # 1. Single-character / single-digit stealth tracking (Roblox style)
    # -------------------------------------------------------------------------
    stripped_char = re.sub(r"^[\s\.\-_,!?;:]+|[\s\.\-_,!?;:]+$", "", content)
    if len(stripped_char) == 1:
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
    detected_types: list[str] = []

    has_phone = bool(_RE_PHONE.search(normalized))
    has_social = bool(_RE_SOCIAL.search(normalized))
    has_dating = bool(_RE_DATING.search(normalized))
    has_address = bool(_RE_ADDRESS.search(normalized))

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
    if is_subscribed and user_disclaimer_approved:
        return ModerationResult(
            content=content,
            is_moderated=False,
            moderation_type=primary_type,
            moderation_disclaimer=disclaimer,
            requires_subscription=False,
        )

    # Mask on original text using matches found on normalized text
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
