"""
Logging setup for VTP Fleet Tracking.
Provides sanitized logging to prevent leaking tokens, passwords, cookies, or secrets.
"""

import logging
import re
import sys

# Regex patterns to detect sensitive parameters in logs
SENSITIVE_PATTERNS = [
    (re.compile(r'(password|pwd|pass|secret)[\'"]?\s*[:=]\s*[\'"][^\'"]+[\'"]', re.IGNORECASE), r'\1: "***"'),
    (re.compile(r'(token|refresh_token|access_token|presence)[\'"]?\s*[:=]\s*[\'"][^\'"]+[\'"]', re.IGNORECASE), r'\1: "***"'),
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._~+/]+=*', re.IGNORECASE), 'Bearer ***'),
]


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            clean_msg = record.msg
            for pattern, repl in SENSITIVE_PATTERNS:
                clean_msg = pattern.sub(repl, clean_msg)
            record.msg = clean_msg
        return True


def setup_logger(name: str = "vtp_fleet") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = setup_logger()
