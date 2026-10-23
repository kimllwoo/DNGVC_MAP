"""
Security Tests: Verifying that tokens, passwords, and sensitive data are sanitized.
"""

import logging
from app.core.logger import setup_logger
from app.core.config import settings


def test_logger_masks_passwords_and_tokens():
    test_logger = setup_logger("test_sec_logger")
    log_records = []

    class MockHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record.getMessage())

    handler = MockHandler()
    test_logger.addHandler(handler)

    test_logger.info('User login payload: password="SuperSecretPassword123" and token="abc_xyz_token_secret"')
    test_logger.info('Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token')

    assert len(log_records) == 2
    assert "SuperSecretPassword123" not in log_records[0]
    assert "***" in log_records[0]
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in log_records[1]
    assert "Bearer ***" in log_records[1]


def test_safe_config_summary_masks_credentials():
    summary = settings.get_safe_summary()
    # Check that plain password strings are not present
    vtr = summary["VTRACKING"]
    assert "password" not in vtr
    assert "password_configured" in vtr

    adsun = summary["ADSUN"]
    assert "password" not in adsun
    assert "password_configured" in adsun
