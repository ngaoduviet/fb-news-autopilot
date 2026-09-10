"""Shared secret redaction for logs, exceptions, and audit artifacts."""
import os
import re


SECRET_ENV_NAMES = ('META_PAGE_ACCESS_TOKEN',)


def configured_secrets():
    return tuple(value for name in SECRET_ENV_NAMES if (value := os.getenv(name)))


def redact(value, secrets=()):
    message = str(value)
    for secret in (*configured_secrets(), *secrets):
        if secret:
            message = message.replace(secret, '[REDACTED]')
    patterns = (
        (r'(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+', r'\1[REDACTED]'),
        (r'(?i)(access[_-]?token\s*[:=]\s*)[^\s&,;]+', r'\1[REDACTED]'),
        (r'(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]'),
        (r'\b(?:EAA|sk-)[A-Za-z0-9_-]{8,}\b', '[REDACTED]'),
    )
    for pattern, replacement in patterns:
        message = re.sub(pattern, replacement, message)
    return message[:500]
