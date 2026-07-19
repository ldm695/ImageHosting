"""Fixtures for browser E2E tests.

These run against a REAL server (a background werkzeug thread on an ephemeral
port) driven by a real Chromium via pytest-playwright. Kept in a separate
top-level `e2e/` dir so the fast `pytest` (testpaths=tests) doesn't collect
them and they don't inherit tests/conftest.py's test_client fixtures.

Run with:  pytest e2e
"""

import os
import socket
import tempfile
import threading

import pytest

# Config reads IMAGEHOSTING_DATA_DIR at import; app.py builds dirs at import.
_BOOTSTRAP_DIR = tempfile.mkdtemp(prefix="ih_e2e_boot_")
os.environ["IMAGEHOSTING_DATA_DIR"] = _BOOTSTRAP_DIR

import app as app_module  # noqa: E402
from config import Config  # noqa: E402


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def live_server():
    """Run the real app in a background thread; yield its base URL."""
    from werkzeug.serving import make_server

    port = _free_port()
    srv = make_server("127.0.0.1", port, app_module.app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        srv.shutdown()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def fresh_data(tmp_path):
    """Point Config at a fresh per-test data dir (server reads Config live)."""
    base = tmp_path / "data"
    Config.DATA_DIR = base
    Config.UPLOAD_DIR = base / "uploads"
    Config.THUMBNAIL_DIR = base / "thumbnails"
    Config.STAGING_DIR = base / "staging"
    Config.ALLOWED_ORIGIN_PORTS = []
    for d in (Config.UPLOAD_DIR, Config.THUMBNAIL_DIR, Config.STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)
    (Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
    (Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
    app_module.SETTINGS_FILE = base / "settings.json"
    yield


@pytest.fixture()
def sample_png(tmp_path):
    """Write a small PNG to disk and return its path (for set_input_files)."""
    from PIL import Image

    p = tmp_path / "sample.png"
    Image.new("RGB", (16, 12), (40, 160, 90)).save(str(p), "PNG")
    return str(p)


@pytest.fixture()
def make_named_png(tmp_path):
    """Factory: create a PNG with a given filename, return its path."""
    from PIL import Image

    def _make(name, color=(80, 80, 200)):
        p = tmp_path / name
        Image.new("RGB", (16, 12), color).save(str(p), "PNG")
        return str(p)

    return _make
