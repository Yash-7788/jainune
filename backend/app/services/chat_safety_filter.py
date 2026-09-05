"""
Roblox-style Smart Chat Safety Filter & Anti-Circumvention Moderation Service.

Enforces:
1. Full platform names in ANY casing combo (InStAgRaM, snapCHAT, FaceBook, WHATSAPP, TeleGram, etc.)
2. Competitor dating app names in ANY casing combo (BUMBLE, TiNdEr, HInGe, sHaAdI, etc.)
3. Shorthand handles with intent disambiguation (insta, gram, snap, wa, sc, tg, fb)
4. Phone numbers (10 digits, formatted, and series of word numbers)
5. Addresses, street names, flat/house numbers, PIN codes, GPS coordinates
6. Generalized intent & idiom filtering:
   - Preserves benign conversational usage (cooking 'grams', 'road trip', 'street food', 'snap decision')
   - Targets actual exchange intent (proper noun streets, dwell verbs, profile handles)
7. Single-character / single-digit sequential stealth tracking across messages:
   - 1st and 2nd single character messages are allowed.
   - Starting on 3rd single character message, character is blocked and converted to '#'.
8. Redirection / masking of all detected sensitive words to '#'.
9. Moderation disclaimer generation & subscription gating.
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
    """Strips zero-width characters and normalizes homoglyphs without corrupting numeric digits."""
    cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad\u2060]", "", text)
    cleaned = unicodedata.normalize("NFKD", cleaned)
    for k, v in _HOMOGLYPH_MAP.items():
        if k in cleaned:
            cleaned = cleaned.replace(k, v)
    return cleaned


# ---------------------------------------------------------------------------
# 1. Full Platform Names (Zero Ambiguity in ANY Casing Combination)
# ---------------------------------------------------------------------------

_FULL_PLATFORMS = [
    # Social Platforms
    r"\bi[\s\.\-_]*n[\s\.\-_]*[s5][\s\.\-_]*t[\s\.\-_]*a[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m\b",
    r"\b[s5][\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t\b",
    r"\bw[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t[\s\.\-_]*[s5][\s\.\-_]*a[\s\.\-_]*p[\s\.\-_]*p\b",
    r"\bt[\s\.\-_]*e[\s\.\-_]*l[\s\.\-_]*e[\s\.\-_]*g[\s\.\-_]*r[\s\.\-_]*a[\s\.\-_]*m\b",
    r"\bf[\s\.\-_]*a[\s\.\-_]*c[\s\.\-_]*e[\s\.\-_]*b[\s\.\-_]*o[\s\.\-_]*o[\s\.\-_]*k\b",
    r"\bt[\s\.\-_]*w[\s\.\-_]*i[\s\.\-_]*t[\s\.\-_]*t[\s\.\-_]*e[\s\.\-_]*r\b",
    r"\bd[\s\.\-_]*i[\s\.\-_]*[s5][\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*r[\s\.\-_]*d\b",
    r"\bx[\s\.\-_]*\.[\s\.\-_]*c[\s\.\-_]*o[\s\.\-_]*m\b",
    r"\bt[\s\.\-_]*h[\s\.\-_]*r[\s\.\-_]*e[\s\.\-_]*a[\s\.\-_]*d[\s\.\-_]*[s5]\b",
    r"\bw[\s\.\-_]*e[\s\.\-_]*c[\s\.\-_]*h[\s\.\-_]*a[\s\.\-_]*t\b",
    r"\b[s5][\s\.\-_]*i[\s\.\-_]*g[\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*l\b",
    # Competitor Dating & Matrimonial Apps
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
_RE_FULL_PLATFORMS = re.compile("|".join(f"(?:{p})" for p in _FULL_PLATFORMS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# 2. Shorthands with Intent Disambiguation
# ---------------------------------------------------------------------------

_SHORTHAND_INTENT = [
    # Insta / 1nsta (unambiguous app shorthand)
    r"\b[i1!][\s\.\-_]*n[\s\.\-_]*[s5][\s\.\-_]*t[\s\.\-_]*a\b",
    # Gram only when used in social handle context
    r"\b(?:my|your|ur|check|on|add|dm|send|the)\s+gram\b",
    r"\bgram\s+(?:handle|id|username|account|profile)\b",
    # Snap with handle / social intent
    r"\b(?:my|your|ur|his|her|add|dm|send|ping|check|on|in)?\s*[s5][\s\.\-_]*n[\s\.\-_]*a[\s\.\-_]*p\s*(?:id|handle|username|me|is|:)?\b",
    # Acronyms with handle / colon notation: my sc is user, sc: user, ig: user, tg: user
    r"\b(?:my\s+)?(?:sc|ig|tg|fb)\s*(?:is|:|=)\s*\w+\b",
    # Action verbs followed by handle markers
    r"\b(?:dm|add|msg|message|ping|text|hit)\s+me\s+(?:on|at)\b",
    # WhatsApp shorthand
    r"\b(?:on|via)\s+wa\b",
    r"\bwa\s*(?:pe|par|me|id|num|number)\b",
]
_RE_SHORTHAND = re.compile("|".join(f"(?:{p})" for p in _SHORTHAND_INTENT), re.IGNORECASE)

# Benign idioms for snap (photograph / decision / weather)
_RE_BENIGN_SNAP = re.compile(
    r"\b(?:snap\s+(?:decision|judgment|shot|dragon)|cold\s+snap|ginger\s+snap|snap\s+out\s+of)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 3. Phone Numbers & Numeric Sequences
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. Addresses, Street Names, PIN Codes & GPS Coordinates
# ---------------------------------------------------------------------------

_ADDRESS_PATTERNS = [
    # 6-digit Indian PIN code (with optional single space/dash e.g. 400 001)
    r"\b[1-9]\d{2}[\s\.\-_]?\d{3}\b",
    # Lat/Long GPS coordinates: e.g. 19.0760, 72.8777
    r"\b[-+]?\d{1,2}\.\d{3,}\s*[,;\s]\s*[-+]?\d{1,3}\.\d{3,}\b",
    # Flat / House / Plot / Bldg / Apartment number
    r"\b(?:flat|house|plot|bldg|building|apt|apartment|sector|block|room|villa|penthouse)\s*(?:no|number)?\.?\s*[0-9a-zA-Z\-/]+\b",
    # Known prominent street / locality names
    r"\b(?:mg|linking|carter|brigade|church|commercial|park|tilak|sv|jm|fc|lavale|koregaon)\s+(?:road|street|rd|marg|lane|park)\b",
    # Numbered street / road: 12th Cross, 4th Main, Road No 5
    r"\b\d+(?:st|nd|rd|th)?\s+(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|cross|main|chowk|rasta|bazaar)\b",
    r"\b(?:street|road|rd|marg|lane|gali|nagar|colony|sector|block|chowk|rasta|bazaar)\s+(?:(?:no|number)\.?\s*)?\d+[a-zA-Z]?\b",
    r"\b(?:sector|block|phase|pocket)\s+[a-zA-Z0-9\-/]+\b",
    # Named colonies, nagars, and enclaves
    r"\b[a-zA-Z0-9\-/]{3,}\s+(?:nagar|colony|enclave|vihar|layout)\b",
    # Location verb + street: live at MG road, meet at church street
    r"\b(?:live\s+at|stay\s+at|house\s+at|flat\s+at|home\s+at|address\s+is|meet\s+at|come\s+to|located\s+at|reach\s+at|near|opposite|behind|next\s+to)\s+[a-zA-Z0-9\s,\-/]{2,25}?(?:road|street|rd|marg|lane|gali|nagar|colony|sector|block|chowk|rasta|bazaar)\b",
]
_RE_ADDRESS = re.compile("|".join(f"(?:{p})" for p in _ADDRESS_PATTERNS), re.IGNORECASE)

# Benign idioms and everyday observations containing 'road' / 'street' (MUST NOT BE MODERATED)
_RE_BENIGN_STREET = re.compile(
    r"\b(?:road\s+trip|hit\s+the\s+road|rocky\s+road|middle\s+of\s+the\s+road|two[\s\-]way\s+street)\b|"
    r"\b(?:street\s+(?:food|smart|smarts|dog|dogs|light|lights|art|play|vendor|vendors|musician|musicians|wear|dance))\b|"
    r"\b(?:down\s+the\s+road|road\s+ahead|long\s+road|empty\s+road|bumpy\s+road|clean\s+road|winding\s+road|clear\s+road|open\s+road)\b|"
    r"\b(?:across\s+the\s+street|walk(?:ed|ing)?\s+down\s+the\s+street|cross(?:ed|ing)?\s+the\s+street|in\s+the\s+street|on\s+the\s+street|off\s+the\s+street)\b|"
    r"\b(?:wall\s+street|baker\s+street|abbey\s+road|sesame\s+street)\b|"
    r"\b(?:the|a|this|that|every|any|one|endless)\s+(?:road|street|lane)\s+(?:of|was|is|are|were|has|have|had|will|seems?|looks?|became)\b",
    re.IGNORECASE,
)


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
    - Case-insensitive full platform matching in any form (InStAgRaM, snapCHAT, etc.)
    - Shorthand matching with intent checks.
    - Preserves benign conversations (cooking grams, idioms, road descriptions).
    - Single-character sequential stealth tracking in Redis (masks 3rd+ single chars).
    - If user is subscribed and approved disclaimer: allows unmasked exchange.
    - Else: masks all occurrences to '#' and attaches disclaimer.
    """
    if not content:
        return ModerationResult(content="", is_moderated=False)

    # Normalized text for pattern matching (unicode homoglyphs & zero-width chars)
    normalized = normalize_text_for_moderation(content)

    # -------------------------------------------------------------------------
    # 1. Single-character / single-digit stealth tracking (Roblox style)
    # -------------------------------------------------------------------------
    stripped_char = re.sub(r"^[\s\.\-_,!?;:]+|[\s\.\-_,!?;:]+$", "", content)
    if len(stripped_char) == 1:
        single_char_key = f"chat:safety:single_chars:{chat_id}:{user_id}"
        count = await redis.incr(single_char_key)
        if count == 1:
            await redis.expire(single_char_key, 86400 * 30)

        if count >= 3:
            return ModerationResult(
                content="#",
                is_moderated=True,
                moderation_type="SINGLE_CHAR_SEQUENCE",
                moderation_disclaimer="Single character sequence detected. Contact information exchange is restricted.",
                requires_subscription=not is_subscribed,
            )
        else:
            return ModerationResult(
                content=content,
                is_moderated=False,
            )

    # -------------------------------------------------------------------------
    # 2. Scan for Violations
    # -------------------------------------------------------------------------
    detected_types: list[str] = []

    # A. Full platform names (unambiguous in ANY casing)
    has_full_platform = bool(_RE_FULL_PLATFORMS.search(normalized))

    # B. Shorthands with contextual intent check
    has_shorthand = False
    if _RE_SHORTHAND.search(normalized):
        # Disambiguate benign idioms for snap
        if "snap" in normalized.lower() and _RE_BENIGN_SNAP.search(normalized):
            has_shorthand = False
        else:
            has_shorthand = True

    # C. Phone numbers & word numbers
    has_phone = bool(_RE_PHONE.search(normalized))

    # D. Address with benign idiom check
    has_address = False
    if _RE_ADDRESS.search(normalized):
        if not _RE_BENIGN_STREET.search(normalized):
            has_address = True

    if has_phone:
        detected_types.append("NUMBERS")
    if has_full_platform or has_shorthand:
        lowered = normalized.lower()
        if any(d in lowered for d in ["tinder", "bumble", "hinge", "shaadi", "jeevansathi", "matrimony"]):
            detected_types.append("DATING_APP")
        else:
            detected_types.append("SOCIAL_ID")
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

    # Mask detected sensitive segments to '#'
    masked_content = content
    masked_content = _RE_PHONE.sub(_mask_match, masked_content)
    masked_content = _RE_FULL_PLATFORMS.sub(_mask_match, masked_content)
    masked_content = _RE_SHORTHAND.sub(_mask_match, masked_content)
    if has_address:
        masked_content = _RE_ADDRESS.sub(_mask_match, masked_content)

    return ModerationResult(
        content=masked_content,
        is_moderated=True,
        moderation_type=primary_type,
        moderation_disclaimer=disclaimer,
        requires_subscription=not is_subscribed,
    )
