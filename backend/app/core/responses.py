"""
Standard response envelope helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid


def ok(data: dict | list, meta: dict | None = None) -> dict:
    return {
        "success": True,
        "data": data,
        "error": None,
        "meta": meta or {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:16]}",
        },
    }


def err(code: str, message: str, details: list | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or []},
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": f"req_{uuid.uuid4().hex[:16]}",
        },
    }
