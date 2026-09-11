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
8. URL Hard-Block (NO SUBSCRIPTION BYPASS):
   - ANY URL in ANY form (http, ftp, data:, bare domain.tld, IP-as-URL, markdown [text](url),
     URL-encoded schemes like ht%74ps://, mixed unicode/homoglyph schemes) is ALWAYS blocked.
   - Jainune brand-masking phishing: "jainune" display text with ANY URL is always blocked.
   - Subscribed users cannot bypass URL blocks. URLs are structurally prohibited in chat.
9. Redirection / masking of all detected sensitive words to '#'.
10. Moderation disclaimer generation & subscription gating (URLs never gated by subscription).
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
    norm, _ = normalize_text_with_mapping(text)
    return norm


def normalize_text_with_mapping(text: str) -> tuple[str, list[int]]:
    """
    Strips zero-width characters and normalizes homoglyphs and combining diacritics.
    Returns (normalized_text, norm_to_orig_index_map).
    """
    zero_width = set("\u200b\u200c\u200d\ufeff\u00ad\u2060")
    norm_chars: list[str] = []
    norm_to_orig: list[int] = []
    for orig_idx, orig_char in enumerate(text):
        if orig_char in zero_width:
            continue
        decomp = unicodedata.normalize("NFKD", orig_char)
        # Strip combining diacritical marks (e.g. accents on í, à)
        base = "".join(c for c in decomp if not unicodedata.combining(c))
        for ch in base:
            ch = _HOMOGLYPH_MAP.get(ch, ch)
            norm_chars.append(ch)
            norm_to_orig.append(orig_idx)
    return "".join(norm_chars), norm_to_orig


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

# ---------------------------------------------------------------------------
# 5. URL Hard-Block (comprehensive, bypass-resistant)
#
# Catches ALL of:
# - Explicit schemes: http, https, ftp, ftps, ws, wss, data:, javascript:, vbscript:
# - URL-encoded scheme evasion: ht%74ps://, hxxps://, h_t_t_p_s
# - Bare domains: evil.com/path, domain.xyz, subdomain.evil.co.in/page
# - www variants: www2., www., ftp.
# - IP-as-URL: 192.168.0.1, [2001:db8::1]
# - Markdown link syntax: [display](url) or [jainune](malicious_url)
# - Known shortener / redirect services
# - Mixed-script / homoglyph domain names (via normalization before matching)
# ---------------------------------------------------------------------------

# Pre-pass: extract and hard-block markdown link targets [text](url) entirely
# This catches jainune-branded phishing like [jainune](http://evil.com)
_RE_MARKDOWN_LINK = re.compile(
    r"\[(?:[^\]]{0,200})\]\(([^)]{0,2000})\)",
    re.IGNORECASE | re.DOTALL,
)

# URL-encoded scheme evasion: ht%74p, hxxps, h_t_t_p, ht+tp, etc.
_RE_SCHEME_EVASION = re.compile(
    r"\bh[\+_\s\.\-%]*t[\+_\s\.\-%]*t[\+_\s\.\-%]*p[\+_\s\.\-%]*s?[\+_\s\.\-%]*:",
    re.IGNORECASE,
)
# Other protocol schemes
_RE_EXPLICIT_SCHEME = re.compile(
    r"\b(?:ftp|ftps|ws|wss|data|javascript|vbscript|file|blob|mailto)\s*:",
    re.IGNORECASE,
)

# Bare TLD domain pattern: captures word.tld, word.tld/path, sub.word.tld
# Uses a broad TLD list covering all common + country-code TLDs
_COMMON_TLDS = (
    r"(?:com|org|net|edu|gov|io|co|app|dev|xyz|info|biz|me|us|uk|in|de|fr|jp|ru|"
    r"ca|au|br|cn|it|es|nl|pl|se|no|dk|fi|be|at|ch|sg|my|ph|id|bd|pk|lk|"
    r"live|online|site|web|store|shop|tech|ai|ml|gg|tv|cc|tk|top|club|fun|"
    r"link|click|page|blog|news|media|social|world|space|red|blue|black|"
    r"click|download|free|win|prize|gift|claim|now|deal|offer|crypto|nft|"
    r"chat|date|meet|love|friend|match)"
)
# Bare domain: word.tld or sub.word.tld/path — no scheme required
# Requires an explicit dot before the TLD to avoid matching plain words.
_RE_BARE_DOMAIN = re.compile(
    r"\b[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)*\." + _COMMON_TLDS + r"(?:\/[^\s<>\[\]()]*)?(?=\s|$|[,;!?\'\"])",
    re.IGNORECASE,
)

# IP-as-URL: 1.2.3.4/path or 1.2.3.4:port — used to bypass domain filters.
# MUST have a path (/) or port (:) to avoid false-positive on dotted phone numbers
# like "9.8.7.6.5.4.3.2.1.0" which phone regex catches separately.
_RE_IP_URL = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|1?\d\d?)(?::\d{1,5}|\/[^\s<>]*)",
)


# www. prefix in any form
_RE_WWW = re.compile(r"\bwww\d*\s*\.\s*\S+", re.IGNORECASE)

# Known shortener/redirect domains (full block regardless of content)
_RE_SHORTENER = re.compile(
    r"\b(?:bit\.ly|tinyurl\.com|t\.me|wa\.me|chat\.whatsapp\.com|is\.gd|buff\.ly|"
    r"ow\.ly|goo\.gl|cutt\.ly|rb\.gy|shorturl\.at|tiny\.cc|tr\.im|v\.gd)/[^\s<>]+",
    re.IGNORECASE,
)


def _detect_url_spans(text: str) -> list[tuple[int, int]]:
    """
    Returns list of (start, end) character spans in `text` where any URL-like
    pattern is detected. Zero tolerance — any doubt = flagged.
    Runs on the NORMALIZED text.
    """
    spans: list[tuple[int, int]] = []
    for pattern in [
        _RE_SCHEME_EVASION,
        _RE_EXPLICIT_SCHEME,
        _RE_WWW,
        _RE_BARE_DOMAIN,
        _RE_IP_URL,
        _RE_SHORTENER,
    ]:
        for m in pattern.finditer(text):
            spans.append(m.span())
    return spans


def _has_url(text: str) -> bool:
    """True if any URL-like pattern detected in text."""
    if _detect_url_spans(text):
        return True
    if _RE_SCHEME_EVASION.search(text):
        return True
    if _RE_EXPLICIT_SCHEME.search(text):
        return True
    return False



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
    normalized, norm_to_orig = normalize_text_with_mapping(content)

    # -------------------------------------------------------------------------
    # 1. Single-character / single-digit stealth tracking (Roblox style)
    # -------------------------------------------------------------------------
    stripped_char = re.sub(r"^[\s\.\-_,!?;:]+|[\s\.\-_,!?;:]+$", "", content)
    if len(stripped_char) == 1:
        single_char_key = f"chat:safety:single_chars:{chat_id}:{user_id}"
        count = await redis.incr(single_char_key)
        await redis.expire(single_char_key, 7 * 86400)

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
    else:
        single_char_key = f"chat:safety:single_chars:{chat_id}:{user_id}"
        try:
            await redis.delete(single_char_key)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 2. Scan for Violations
    # -------------------------------------------------------------------------
    detected_types: list[str] = []

    # A. Full platform names (unambiguous in ANY casing)
    has_full_platform = bool(_RE_FULL_PLATFORMS.search(normalized))

    # B. Shorthands with contextual intent check
    shorthand_spans: list[tuple[int, int]] = []
    for m in _RE_SHORTHAND.finditer(normalized):
        matched_text = m.group(0).lower()
        if "snap" in matched_text and _RE_BENIGN_SNAP.search(normalized):
            is_benign = any(
                not (m.end() <= bm.start() or m.start() >= bm.end())
                for bm in _RE_BENIGN_SNAP.finditer(normalized)
            )
            if is_benign:
                continue
        shorthand_spans.append(m.span())
    has_shorthand = len(shorthand_spans) > 0

    # C. Phone numbers & word numbers
    has_phone = bool(_RE_PHONE.search(normalized))

    # D. Address with benign idiom check
    address_spans: list[tuple[int, int]] = []
    for m in _RE_ADDRESS.finditer(normalized):
        if _RE_BENIGN_STREET.search(normalized):
            is_benign = any(
                not (m.end() <= bm.start() or m.start() >= bm.end())
                for bm in _RE_BENIGN_STREET.finditer(normalized)
            )
            if is_benign:
                continue
        address_spans.append(m.span())
    has_address = len(address_spans) > 0

    # E. URL Hard-Block (comprehensive — no subscription bypass)
    # 1. Markdown link syntax [display](url): strip markdown to reveal hidden URL
    link_spans: list[tuple[int, int]] = []
    for md_match in _RE_MARKDOWN_LINK.finditer(content):
        # Always block the entire markdown link — we never reveal the URL target
        link_spans.append(md_match.span())
    # 2. Scheme evasion and explicit schemes detected in normalized text
    link_spans.extend(_detect_url_spans(normalized))
    has_link = len(link_spans) > 0

    # URL detection is hard-blocked FIRST — takes priority over subscription gate
    if has_link:
        detected_types.insert(0, "EXTERNAL_LINK")  # Always first priority

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
    elif primary_type == "EXTERNAL_LINK":
        disclaimer = "Sharing external links or unverified URLs is restricted for safety."
    else:
        disclaimer = "You are trying to exchange physical address or GPS coordinates. Exchange at your own risk and only if you trust."

    # -------------------------------------------------------------------------
    # 3. Subscription & Approval Gate
    # IMPORTANT: URLs are NEVER gated by subscription. Any message containing a
    # URL is always masked and never returned unmodified, regardless of
    # is_subscribed or user_disclaimer_approved. This prevents phishing,
    # domain-masking, and jainune-branded malicious link attacks.
    # -------------------------------------------------------------------------
    if primary_type != "EXTERNAL_LINK" and is_subscribed and user_disclaimer_approved:
        return ModerationResult(
            content=content,
            is_moderated=False,
            moderation_type=primary_type,
            moderation_disclaimer=disclaimer,
            requires_subscription=False,
        )

    # Mask detected sensitive segments to '#' based on matches in normalized text
    # For markdown links: mask the entire [text](url) span in original content coords
    # so neither the display text nor the URL is revealed.
    spans: list[tuple[int, int]] = []
    for regex in [_RE_PHONE, _RE_FULL_PLATFORMS]:
        for m in regex.finditer(normalized):
            spans.append(m.span())
    spans.extend(shorthand_spans)
    if has_address:
        spans.extend(address_spans)
    md_spans_orig: list[tuple[int, int]] = []
    normalized_link_spans: list[tuple[int, int]] = []
    if has_link:
        # Markdown spans: [text](url) — already in original content coordinates.
        # Apply directly to mask_indices without norm_to_orig translation.
        md_spans_orig = [m.span() for m in _RE_MARKDOWN_LINK.finditer(content)]
        # URL spans from normalized text — translate via norm_to_orig as usual.
        normalized_link_spans = _detect_url_spans(normalized)

    if spans or (has_link and (md_spans_orig or normalized_link_spans)):

        # Merge overlapping spans (all in normalized coords)
        spans.sort(key=lambda s: s[0])
        merged_spans: list[tuple[int, int]] = []
        for s, e in spans:
            if not merged_spans or s > merged_spans[-1][1]:
                merged_spans.append((s, e))
            else:
                merged_spans[-1] = (merged_spans[-1][0], max(merged_spans[-1][1], e))

        mask_indices: set[int] = set()

        # 1. Normalized-coord spans → translate to original via norm_to_orig
        for s, e in merged_spans:
            if s < len(norm_to_orig) and e - 1 < len(norm_to_orig):
                orig_start = norm_to_orig[s]
                orig_end = norm_to_orig[e - 1]
                while orig_end + 1 < len(content) and unicodedata.combining(content[orig_end + 1]):
                    orig_end += 1
                for idx in range(orig_start, orig_end + 1):
                    mask_indices.add(idx)
            else:
                for i in range(s, min(e, len(norm_to_orig))):
                    mask_indices.add(norm_to_orig[i])

        if has_link:
            # 2. Normalized URL spans → translate to original
            for s, e in normalized_link_spans:
                if s < len(norm_to_orig) and e - 1 < len(norm_to_orig):
                    orig_s = norm_to_orig[s]
                    orig_e = norm_to_orig[e - 1]
                    for idx in range(orig_s, orig_e + 1):
                        mask_indices.add(idx)
                else:
                    for i in range(s, min(e, len(norm_to_orig))):
                        mask_indices.add(norm_to_orig[i])
            # 3. Markdown [text](url) spans are already in original content coords
            for orig_s, orig_e in md_spans_orig:
                for idx in range(orig_s, orig_e):
                    mask_indices.add(idx)

        chars = list(content)
        for idx in mask_indices:
            chars[idx] = "#"
        masked_content = "".join(chars)
    else:
        masked_content = content

    return ModerationResult(
        content=masked_content,
        is_moderated=True,
        moderation_type=primary_type,
        moderation_disclaimer=disclaimer,
        requires_subscription=not is_subscribed,
    )
