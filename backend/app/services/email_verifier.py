"""
Email & Bot Verification Service:
- Whitelist of trusted consumer & business email providers (Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, etc.).
- Smart detection and rejection of disposable, throwaway, and custom ephemeral email domains.
- Anti-bot and client integrity verification.
"""

from __future__ import annotations

import logging
import re
import socket
from typing import Tuple

from app.core.config import settings

log = logging.getLogger(__name__)

# Trusted and approved primary email providers
_ALLOWED_POPULAR_DOMAINS = {
    # Google
    "gmail.com", "googlemail.com",
    # Microsoft
    "outlook.com", "hotmail.com", "live.com", "msn.com", "windowslive.com",
    "outlook.in", "hotmail.co.in", "live.in", "hotmail.co.uk", "hotmail.fr", "hotmail.es", "hotmail.it",
    # Yahoo
    "yahoo.com", "yahoo.co.in", "yahoo.in", "yahoo.co.uk", "ymail.com", "rocketmail.com", "myyahoo.com",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # Proton
    "proton.me", "protonmail.com",
    # Zoho
    "zoho.com", "zohomail.in", "zoho.in",
    # Indian Demographics
    "rediffmail.com", "sify.com",
    # Other Major Global Providers
    "aol.com", "gmx.com", "gmx.net", "mail.com", "web.de", "t-online.de",
    "fastmail.com", "fastmail.fm", "hey.com",
    # Official app domain
    "jainune.com",
}

# Known public disposable / temporary email domains (black-list fallback)
_DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "tempmail.com", "temp-mail.org", "10minutemail.com", "10minutemail.net",
    "throwawaymail.com", "trashmail.com", "trashmail.net", "trashmail.org",
    "yopmail.com", "yopmail.fr", "yopmail.net", "sharklasers.com", "getairmail.com",
    "dispostable.com", "crazymailing.com", "burnermail.io", "mytemp.email",
    "nada.ltd", "dropmail.me", "mohmal.com", "generator.email", "inboxbear.com",
    "fakemailgenerator.com", "emailondeck.com", "getnada.com", "maildrop.cc",
    "tempr.email", "disposablemail.com", "discard.email", "spamgourmet.com",
    "harakirimail.com", "tmail.ws", "guerrillamailblock.com", "grr.la",
    "pokemail.net", "tempail.com", "inboxkitten.com", "bupmail.com",
    "crazymailing.com", "fakemail.net", "jetable.org", "byom.de",
    "mytempemail.com", "mytempmail.com", "nowmymail.com", "safe-mail.net",
    "spambox.us", "trashymail.com", "trashinbox.com", "incognitomail.com",
}

# Suspicious keywords in domain names that indicate generated ephemeral domains
_DISPOSABLE_KEYWORDS = {
    "temp", "dispos", "burner", "throwaway", "fake", "trash", "guerrilla",
    "junk", "sharklaser", "generator", "inboxbear", "spam4", "minute",
    "nowmymail", "byom", "fakemail", "mohmal", "discard", "mailcatch",
    "anonymbox", "tempinbox", "disbox", "guerrilla", "spambox",
}

# Suspicious high-abuse free TLDs
_SUSPICIOUS_TLDS = {
    ".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".buzz", ".rest", ".country",
    ".click", ".link", ".work",
}


def is_disposable_email(email: str, allow_custom_domains: bool = False) -> Tuple[bool, str]:
    """
    Validates an email address against:
    1. Fast allowlist of trusted consumer email providers (Gmail, Outlook, Yahoo, Apple, etc.).
    2. Strict rejection of unknown/untrusted/disposable domains.
    Returns (is_disposable_or_unallowed: bool, reason_message: str).
    """
    if not email or "@" not in email:
        return True, "Invalid email address format."

    clean_email = email.strip().lower()

    # Basic RFC 5322 syntax check
    match = re.match(r"^([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)$", clean_email)
    if not match:
        return True, "Invalid email address format."

    local_part, domain = match.groups()

    # 1. Immediate Allowlist Pass for standard reputable providers
    if domain in _ALLOWED_POPULAR_DOMAINS:
        return False, ""

    # 2. Check for subdomain of allowed provider (e.g. mail.yahoo.com)
    domain_parts = domain.split(".")
    if len(domain_parts) > 2:
        root_domain = ".".join(domain_parts[-2:])
        if root_domain in _ALLOWED_POPULAR_DOMAINS:
            return False, ""

    # 3. If allowlist is strictly enforced, reject unapproved/custom domains
    if not allow_custom_domains:
        return True, "Please use a supported email provider (Gmail, Outlook, Yahoo, iCloud, Proton, Zoho, or Rediffmail)."

    # 4. Fallback checks for custom domains:
    # 4a. Exact match on known disposable list
    if domain in _DISPOSABLE_DOMAINS:
        return True, "Temporary or disposable email addresses are not permitted."

    # 4b. Subdomain check on disposable list
    if len(domain_parts) > 2 and ".".join(domain_parts[-2:]) in _DISPOSABLE_DOMAINS:
        return True, "Temporary or disposable email addresses are not permitted."

    # 4c. Keyword heuristic on custom domains
    domain_name = domain_parts[0]
    for kw in _DISPOSABLE_KEYWORDS:
        if kw in domain_name:
            return True, "Disposable or burner email addresses are not allowed on Jainune."

    # 4d. TLD check for spam/burner TLDs
    for tld in _SUSPICIOUS_TLDS:
        if domain.endswith(tld):
            return True, "Email domain is not supported for verification."

    # 4e. DNS host resolution failsafe
    try:
        socket.gethostbyname(domain)
    except (socket.gaierror, socket.herror, TimeoutError, OSError):
        return True, "Email domain could not be resolved or has no valid mail servers."

    return False, ""


def verify_bot_integrity(
    headers: dict,
    turnstile_token: str | None = None,
    is_production: bool = False,
) -> Tuple[bool, str]:
    """
    Validates client request to detect automated bot scripts and scrapers.
    Returns (is_bot: bool, reason_message: str).
    """
    user_agent = headers.get("user-agent", "").lower()

    # 1. Block known automated scripts & scrapers in production
    blocked_agents = [
        "python-requests", "curl/", "wget/", "scrapy", "postmanruntime",
        "go-http-client", "httpie", "aiohttp", "urllib", "puppeteer",
    ]
    if any(agent in user_agent for agent in blocked_agents):
        return True, "Automated or unsupported client detected."

    # 2. In production, turnstile_token verification can be enforced
    if is_production and turnstile_token:
        if len(turnstile_token) < 10:
            return True, "Security verification challenge failed."

    return False, ""
