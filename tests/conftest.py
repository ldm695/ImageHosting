"""Pytest fixtures for ImageHosting.

Each test runs against a fresh temp data directory so nothing touches the
user's real ~/AppData store and tests don't leak state into each other.
"""
import os
import io
import tempfile

import pytest

# Config reads IMAGEHOSTING_DATA_DIR at import time and app.py creates its
# directories at import, so a valid temp dir must exist before importing app.
_BOOTSTRAP_DIR = tempfile.mkdtemp(prefix='ih_boot_')
os.environ['IMAGEHOSTING_DATA_DIR'] = _BOOTSTRAP_DIR

import app as app_module  # noqa: E402
import staging as staging_module  # noqa: E402
from config import Config  # noqa: E402

# Config defaults that individual tests may mutate; restored each test.
_DEFAULT_STAGING_TIMEOUT = Config.STAGING_TIMEOUT
_DEFAULT_STAGING_MAX_FILES = Config.STAGING_MAX_FILES


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    """Point Config + settings file at a fresh per-test directory.

    Also clears any staged-upload timers left over from a previous test so
    the module-global `_staging_timers` dict can't leak state (it survives
    across tests otherwise, which would skew the MAX_FILES limit).
    """
    base = tmp_path / 'data'
    Config.DATA_DIR = base
    Config.UPLOAD_DIR = base / 'uploads'
    Config.THUMBNAIL_DIR = base / 'thumbnails'
    Config.STAGING_DIR = base / 'staging'
    Config.ALLOWED_ORIGIN_PORTS = []
    Config.STAGING_TIMEOUT = _DEFAULT_STAGING_TIMEOUT
    Config.STAGING_MAX_FILES = _DEFAULT_STAGING_MAX_FILES
    for d in (Config.UPLOAD_DIR, Config.THUMBNAIL_DIR, Config.STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)
    (Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
    (Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
    app_module.SETTINGS_FILE = base / 'settings.json'

    with staging_module._staging_lock:
        for t in staging_module._staging_timers.values():
            t.cancel()
        staging_module._staging_timers.clear()

    yield

    with staging_module._staging_lock:
        for t in staging_module._staging_timers.values():
            t.cancel()
        staging_module._staging_timers.clear()


@pytest.fixture()
def client():
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture()
def png_bytes():
    """A small valid PNG as raw bytes."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (12, 8), (200, 30, 30)).save(buf, 'PNG')
    return buf.getvalue()


def make_png(w=10, h=10, color=(0, 100, 200)):
    """Return raw bytes of a small PNG."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (w, h), color).save(buf, 'PNG')
    return buf.getvalue()


def upload_png(client, name, group=None, data_bytes=None, tag=None):
    """Helper: upload one PNG via /api/upload. Returns the response."""
    if data_bytes is None:
        data_bytes = make_png()
    payload = {'files': (io.BytesIO(data_bytes), name)}
    if tag is not None:
        payload['tag'] = tag
    url = '/api/upload'
    if group:
        url += f'?group={group}'
    return client.post(url, data=payload, content_type='multipart/form-data')


def stage_file(client, name, data_bytes=None, group=None, tag=None):
    """Helper: stage one file via /api/upload/stage. Returns the response."""
    if data_bytes is None:
        data_bytes = make_png()
    url = '/api/upload/stage'
    params = []
    if group:
        params.append(f'group={group}')
    if tag is not None:
        params.append(f'tag={tag}')
    if params:
        url += '?' + '&'.join(params)
    return client.post(url, data={'files': (io.BytesIO(data_bytes), name)},
                       content_type='multipart/form-data')
