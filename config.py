"""
ImageHosting configuration
Supports environment variables and CLI arguments to override defaults
"""

import os
import sys
from pathlib import Path


def get_default_data_dir() -> Path:
    """Get the platform-standard data directory"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / "ImageHosting"


class Config:
    # ── Server ─────────────────────────────────────
    HOST = "0.0.0.0"  # Listen on all interfaces (LAN access)
    PORT = int(os.environ.get("IMAGEHOSTING_PORT", 6951))

    # ── Storage paths ──────────────────────────────
    DATA_DIR = Path(os.environ.get("IMAGEHOSTING_DATA_DIR", str(get_default_data_dir())))
    UPLOAD_DIR = DATA_DIR / "uploads"
    THUMBNAIL_DIR = DATA_DIR / "thumbnails"

    # ── Upload limits ──────────────────────────────
    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    # ── Staging (upload confirmation) ───────────────
    STAGING_DIR = DATA_DIR / "staging"
    STAGING_TIMEOUT = 300  # Default 5 minutes
    STAGING_MAX_FILES = 100  # Anti-abuse limit

    # ── Thumbnails ─────────────────────────────────
    THUMBNAIL_SIZE = (400, 400)  # (width, height) in pixels
    THUMBNAIL_QUALITY = 85

    # Formats that Pillow can process (SVG/ICO skip thumbnails)
    PILLOW_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

    # ── Groups ─────────────────────────────────────
    DEFAULT_GROUP = "general"

    # ── CORS ────────────────────────────────────────
    # Cross-origin requests are allowed only from these ports (on localhost /
    # 127.0.0.1 / the LAN IP). Empty list = same-origin only (most secure).
    # Evaluated per-request, so changes take effect without a restart.
    ALLOWED_ORIGIN_PORTS: list = []

    # ── Theme ───────────────────────────────────────
    THEME = "auto"  # auto | light | dark

    # ── Page ───────────────────────────────────────
    SITE_TITLE = "ImageHosting"
