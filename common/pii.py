"""
PII Sanitiser (FR-02).

Applied to every mirrored request BEFORE it is sent to the sandbox replica or
written to telemetry storage, so no real sensitive data ever leaves the
production path in cleartext.

Uses an allow-list / deny-list field-masking approach (per the mitigation
plan in Section 12.2, risk #4 of the Review-II document) rather than a
generic regex-only approach, because field names are more reliable than
pattern-matching for structured JSON payloads. Regex patterns are kept as a
second layer for free-text fields.
"""
import re
import copy

# Field names that are always masked, wherever they appear in a JSON body,
# regardless of nesting depth.
DENY_LIST_FIELDS = {
    "password", "pwd", "secret", "token", "api_key", "apikey",
    "authorization", "email", "phone", "phone_number", "ssn",
    "aadhaar", "pan", "credit_card", "card_number", "cvv",
    "address", "dob", "date_of_birth", "otp",
}

# Regex fallback for free-text fields that aren't caught by field-name masking.
PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL_REDACTED]"),
    (re.compile(r"\b\d{10}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"), "[CARD_REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
]

REDACTED = "[REDACTED]"


def _mask_string(value: str) -> str:
    for pattern, replacement in PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def sanitize(obj):
    """Recursively sanitise a JSON-like structure (dict / list / scalar)."""
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            if key.lower() in DENY_LIST_FIELDS:
                cleaned[key] = REDACTED
            else:
                cleaned[key] = sanitize(value)
        return cleaned
    if isinstance(obj, list):
        return [sanitize(item) for item in obj]
    if isinstance(obj, str):
        return _mask_string(obj)
    return obj


def sanitize_headers(headers: dict) -> dict:
    """Strip auth/cookie headers before mirroring — these never need to reach the sandbox."""
    cleaned = copy.deepcopy(dict(headers))
    for h in list(cleaned.keys()):
        if h.lower() in ("authorization", "cookie", "set-cookie", "x-api-key"):
            cleaned[h] = REDACTED
    return cleaned
