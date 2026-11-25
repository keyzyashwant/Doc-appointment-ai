"""Phone normalization for Indian mobile numbers.

Accepts 10-digit Indian mobile (starts 6-9) with optional +91/91/0 prefix.
Strips spaces, dashes, parentheses.  Stores as "+91XXXXXXXXXX".
"""

import re

from app.core.exceptions import DomainError, ErrorCode

_STRIP_RE = re.compile(r"[\s\-\(\)]+")
_PHONE_RE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")


def normalize_phone(raw: str) -> str:
    """Return '+91XXXXXXXXXX' or raise DomainError(INVALID_PHONE)."""
    cleaned = _STRIP_RE.sub("", raw)
    match = _PHONE_RE.match(cleaned)
    if not match:
        raise DomainError(ErrorCode.INVALID_PHONE, f"Invalid Indian mobile number: {raw}")
    return f"+91{match.group(1)}"
