"""
Configuration management for VTP Fleet Tracking.
Loads environment variables safely without hardcoding sensitive secrets.
"""

import os
from typing import Dict, Any
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env if present
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


class Settings:
    # Server network settings
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Viettel VTracking GPS Provider (Account 1)
    VTRACKING_ENABLED: bool = os.getenv("VTRACKING_ENABLED", "false").lower() in ("true", "1", "yes")
    VTRACKING_BASE_URL: str = os.getenv("VTRACKING_BASE_URL", "https://vtracking2.viettel.vn")
    VTRACKING_USERNAME: str = os.getenv("VTRACKING_USERNAME", "")
    VTRACKING_PASSWORD: str = os.getenv("VTRACKING_PASSWORD", "")
    VTRACKING_ORG_ID: str = os.getenv("VTRACKING_ORG_ID", "")
    VTRACKING_TIMEOUT_SECONDS: int = int(os.getenv("VTRACKING_TIMEOUT_SECONDS", "15"))

    # Adsun GPS Provider (Account 1)
    ADSUN_ENABLED: bool = os.getenv("ADSUN_ENABLED", "false").lower() in ("true", "1", "yes")
    ADSUN_AUTH_URL: str = os.getenv("ADSUN_AUTH_URL", "https://auth.adsun.vn/Auth/LoginV4")
    ADSUN_API_URL: str = os.getenv("ADSUN_API_URL", "https://dinhvi.adsun.vn")
    ADSUN_USERNAME: str = os.getenv("ADSUN_USERNAME", "")
    ADSUN_PASSWORD: str = os.getenv("ADSUN_PASSWORD", "")
    ADSUN_TIMEOUT_SECONDS: int = int(os.getenv("ADSUN_TIMEOUT_SECONDS", "15"))

    # Excel Data Files (Auto fallback to local data_excel/ on Windows)
    _default_dng_candidate = Path("/home/vtp-dng-hoangtv/Workspace/Download/Danh sách xe DNG.xlsx")
    if not _default_dng_candidate.exists():
        _local_dng = ROOT_DIR / "data_excel" / "Danh sách xe DNG.xlsx"
        if _local_dng.exists():
            _default_dng_candidate = _local_dng

    _default_full_candidate = Path("/home/vtp-dng-hoangtv/Workspace/Download/Danh_sach_xe_10-10-2026.xlsx")
    if not _default_full_candidate.exists():
        _local_full = ROOT_DIR / "data_excel" / "Danh_sach_xe_10-10-2026.xlsx"
        if _local_full.exists():
            _default_full_candidate = _local_full

    EXCEL_DANH_SACH_XE_DNG_PATH: str = os.getenv(
        "EXCEL_DANH_SACH_XE_DNG_PATH",
        str(_default_dng_candidate),
    )
    EXCEL_DANH_SACH_XE_PATH: str = os.getenv(
        "EXCEL_DANH_SACH_XE_PATH",
        str(_default_full_candidate),
    )

    # Sync & Cache Settings
    GPS_CACHE_TTL_SECONDS: int = int(os.getenv("GPS_CACHE_TTL_SECONDS", "60"))
    GPS_STALE_THRESHOLD_SECONDS: int = int(os.getenv("GPS_STALE_THRESHOLD_SECONDS", "1800"))
    ENABLE_DEMO_MOCK_FALLBACK: bool = os.getenv("ENABLE_DEMO_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")

    @classmethod
    def get_safe_summary(cls) -> Dict[str, Any]:
        """Return configuration dictionary with all secrets masked."""
        return {
            "HOST": cls.HOST,
            "PORT": cls.PORT,
            "DEBUG": cls.DEBUG,
            "VTRACKING": {
                "enabled": cls.VTRACKING_ENABLED,
                "base_url": cls.VTRACKING_BASE_URL,
                "username_configured": bool(cls.VTRACKING_USERNAME),
                "password_configured": bool(cls.VTRACKING_PASSWORD),
                "timeout": cls.VTRACKING_TIMEOUT_SECONDS,
            },
            "ADSUN": {
                "enabled": cls.ADSUN_ENABLED,
                "auth_url": cls.ADSUN_AUTH_URL,
                "api_url": cls.ADSUN_API_URL,
                "username_configured": bool(cls.ADSUN_USERNAME),
                "password_configured": bool(cls.ADSUN_PASSWORD),
                "timeout": cls.ADSUN_TIMEOUT_SECONDS,
            },
            "EXCEL": {
                "danh_sach_xe_dng_exists": Path(cls.EXCEL_DANH_SACH_XE_DNG_PATH).exists(),
                "danh_sach_xe_exists": Path(cls.EXCEL_DANH_SACH_XE_PATH).exists(),
            },
            "DEMO_MOCK_FALLBACK": cls.ENABLE_DEMO_MOCK_FALLBACK,
        }


settings = Settings()
