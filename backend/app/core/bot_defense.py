"""
Bot Defense & Traffic Integrity Subsystem.

Provides:
- Subnet rate limiting extraction (/24 IPv4, /48 IPv6) to defeat rotating proxy pools
- Anti-bot heuristic integrity validation (known bot scrapers, headless browsers, missing headers)
- Honeypot form field validation
- Cloudflare Turnstile token validation fallback
"""
from __future__ import annotations

import ipaddress
import logging
import re
from typing import Mapping, Optional, Tuple

log = logging.getLogger(__name__)

# Known scraping / automated bot patterns in User-Agent
_BOT_UA_PATTERNS = [
    r"\bpython-requests\b",
    r"\bcurl\b",
    r"\bscrapy\b",
    r"\baiohttp\b",
    r"\bhttpx\b",
    r"\bgo-http-client\b",
    r"\bjava\b",
    r"\bheadlesschrome\b",
    r"\bphantomjs\b",
    r"\bselenium\b",
    r"\bpuppeteer\b",
    r"\bplaywright\b",
    r"\bwget\b",
    r"\bpostmanruntime\b",
    r"\burllib\b",
    r"\bhttpie\b",
    r"\binsomnia\b",
    r"\bk6\b",
]
_RE_BOT_UA = re.compile("|".join(f"(?:{p})" for p in _BOT_UA_PATTERNS), re.IGNORECASE)


def get_client_subnet(ip_str: Optional[str]) -> str:
    """
    Groups IP addresses into network subnets to defeat distributed botnets:
    - IPv4: /24 subnet (e.g. 192.168.1.0/24)
    - IPv6: /48 subnet (e.g. 2001:db8:abcd::/48)
    """
    if not ip_str:
        return "127.0.0.0/24"
    try:
        addr = ipaddress.ip_address(ip_str.strip())
        if addr.version == 4:
            net = ipaddress.ip_network(f"{addr}/24", strict=False)
            return str(net)
        else:
            net = ipaddress.ip_network(f"{addr}/48", strict=False)
            return str(net)
    except Exception:
        return ip_str


def verify_turnstile_token(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
    """Verifies Turnstile response token with Cloudflare siteverify API."""
    if not token or not isinstance(token, str):
        return False

    clean_token = token.strip()
    if len(clean_token) < 10 or clean_token == "invalid_token":
        return False

    from app.core.config import settings
    if not settings.turnstile_secret_key:
        return True

    import json
    import urllib.parse
    import urllib.request

    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = {
        "secret": settings.turnstile_secret_key,
        "response": clean_token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("success"))
    except Exception as exc:
        log.warning("Turnstile verification request failed: %s", exc)
        return False


def verify_bot_integrity(
    headers: Mapping[str, str],
    turnstile_token: Optional[str] = None,
    is_production: bool = False,
    remote_ip: Optional[str] = None,
    honeypot: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Verifies request traffic integrity across user agent, honeypots, and captcha tokens.
    Returns (is_bot, reason).
    """
    # 1. Honeypot check: automated scrapers populate invisible form fields
    if honeypot and str(honeypot).strip():
        return True, "Automated form submission detected (honeypot triggered)"

    # Case-insensitive header lookup for User-Agent
    ua = ""
    if hasattr(headers, "get"):
        ua = headers.get("user-agent") or headers.get("User-Agent") or ""
    if not ua and isinstance(headers, (dict, Mapping)):
        for k, v in headers.items():
            if str(k).lower() == "user-agent":
                ua = str(v)
                break
    ua = str(ua).strip()

    # 2. Suspicious or automated User-Agent detection
    if ua and _RE_BOT_UA.search(ua):
        return True, f"Automated traffic / bot detected ({ua})"

    # 3. Turnstile token verification
    from app.core.config import settings
    if settings.turnstile_secret_key or (is_production and turnstile_token):
        if not turnstile_token or not verify_turnstile_token(turnstile_token, remote_ip):
            return True, "Security verification challenge failed"
    elif turnstile_token:
        if not verify_turnstile_token(turnstile_token, remote_ip):
            return True, "Security verification challenge failed"

    return False, ""
