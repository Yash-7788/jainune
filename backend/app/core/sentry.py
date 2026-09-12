"""
Sentry configuration with strict PII scrubbing and deterministic error fingerprinting.
"""
import re
from typing import Any, Dict, Optional

SENSITIVE_KEYS = {
    "authorization", "cookie", "set-cookie", "token", "password",
    "otp", "pepper", "secret", "phone", "phone_number", "email",
    "access_token", "refresh_token", "razorpay_key_secret", "key"
}

PHONE_REGEX = re.compile(r"(\+?91)?[6-9]\d{9}")
OTP_REGEX = re.compile(r"\b\d{6}\b")


def scrub_pii_from_dict(data: Any) -> Any:
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_KEYS):
                cleaned[k] = "[SCRUBBED]"
            else:
                cleaned[k] = scrub_pii_from_dict(v)
        return cleaned
    elif isinstance(data, list):
        return [scrub_pii_from_dict(item) for item in data]
    elif isinstance(data, str):
        # Mask phone numbers in strings
        scrubbed = PHONE_REGEX.sub("[PHONE_SCRUBBED]", data)
        return scrubbed
    return data


def sentry_before_send(event: Dict[str, Any], hint: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Hook executed before sending an event to Sentry.
    Enforces zero-PII leakage and groups errors cleanly.
    """
    # 1. Scrub HTTP Request headers, body, cookies & query_string
    if "request" in event:
        req = event["request"]
        if "headers" in req:
            req["headers"] = scrub_pii_from_dict(req["headers"])
        if "data" in req:
            req["data"] = scrub_pii_from_dict(req["data"])
        if "cookies" in req:
            req["cookies"] = "[SCRUBBED]"
        if "query_string" in req and isinstance(req["query_string"], str):
            req["query_string"] = PHONE_REGEX.sub("[PHONE_SCRUBBED]", req["query_string"])
            for sensitive_key in SENSITIVE_KEYS:
                req["query_string"] = re.sub(
                    rf"({sensitive_key}=)[^&]+",
                    r"\1[SCRUBBED]",
                    req["query_string"],
                    flags=re.IGNORECASE,
                )

    # 2. Scrub user context if attached
    if "user" in event:
        event["user"] = scrub_pii_from_dict(event["user"])

    # 3. Scrub extra, contexts, and breadcrumbs (SECOND-029)
    if "extra" in event:
        event["extra"] = scrub_pii_from_dict(event["extra"])
    if "contexts" in event:
        event["contexts"] = scrub_pii_from_dict(event["contexts"])
    if "breadcrumbs" in event:
        event["breadcrumbs"] = scrub_pii_from_dict(event["breadcrumbs"])

    # 4. Deterministic Error Fingerprinting for Sentry issue grouping
    if hint and "exc_info" in hint:
        exc_type, exc_value, _ = hint["exc_info"]
        if exc_type is not None:
            type_name = exc_type.__name__
            module_name = getattr(exc_type, "__module__", "")

            if "asyncpg" in module_name or "Postgres" in type_name:
                event["fingerprint"] = ["database-error", type_name]
            elif "redis" in module_name or "Redis" in type_name:
                event["fingerprint"] = ["redis-error", type_name]
            elif "pydantic" in module_name or "ValidationError" in type_name:
                event["fingerprint"] = ["validation-error", type_name]
            elif "HTTPException" in type_name:
                status_code = getattr(exc_value, "status_code", 500)
                event["fingerprint"] = ["http-exception", str(status_code)]
            elif "razorpay" in module_name or "Razorpay" in type_name:
                event["fingerprint"] = ["payment-gateway-error", type_name]

    return event


def init_sentry(dsn: str, environment: str, traces_sample_rate: float = 0.1):
    """
    Initializes Sentry SDK with strict PII scrubbing and custom fingerprinting.
    """
    if not dsn:
        return

    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,
            before_send=sentry_before_send,
        )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to initialize Sentry SDK: %s", exc)
