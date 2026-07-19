"""Staging (stage / confirm / cancel) edge cases."""
import io

from conftest import stage_file, upload_png, make_png
from config import Config


def test_stage_returns_token_and_preview(client, png_bytes):
    r = stage_file(client, 'p.png', png_bytes)
    assert r.status_code == 200
    body = r.get_json()
    assert len(body['token']) == 32
    assert body['preview'].startswith('data:image/')
    assert body['expires_in'] == Config.STAGING_TIMEOUT


def test_stage_invalid_group(client, png_bytes):
    r = stage_file(client, 'p.png', png_bytes, group='../bad')
    assert r.status_code == 400


def test_stage_unsupported_format(client):
    r = stage_file(client, 'note.txt', b'hello')
    assert r.status_code == 400


def test_stage_conflict_when_already_uploaded(client, png_bytes):
    upload_png(client, 'dup.png')
    r = stage_file(client, 'dup.png', png_bytes)
    assert r.status_code == 409


def test_stage_max_files_limit(client, png_bytes):
    Config.STAGING_MAX_FILES = 1
    assert stage_file(client, 'a.png', png_bytes).status_code == 200
    r = stage_file(client, 'b.png', png_bytes)
    assert r.status_code == 429


def test_confirm_with_group_override(client, png_bytes):
    client.post('/api/groups', json={'name': 'archive'})
    token = stage_file(client, 'ov.png', png_bytes).get_json()['token']
    r = client.post('/api/upload/confirm', json={'token': token, 'group': 'archive'})
    assert r.status_code == 200 and r.get_json()['group'] == 'archive'
    assert (Config.UPLOAD_DIR / 'archive' / 'ov.png').exists()


def test_confirm_applies_preset_tag(client, png_bytes):
    token = stage_file(client, 't.png', png_bytes, tag='preset').get_json()['token']
    r = client.post('/api/upload/confirm', json={'token': token})
    assert r.get_json().get('tag') == 'preset'


def test_confirm_tag_override_and_clear(client, png_bytes):
    # Override
    tok1 = stage_file(client, 'a.png', png_bytes, tag='preset').get_json()['token']
    r = client.post('/api/upload/confirm', json={'token': tok1, 'tag': 'override'})
    assert r.get_json().get('tag') == 'override'
    # Explicit empty string clears
    tok2 = stage_file(client, 'b.png', png_bytes, tag='preset').get_json()['token']
    r = client.post('/api/upload/confirm', json={'token': tok2, 'tag': ''})
    assert 'tag' not in r.get_json()


def test_confirm_unknown_token_404(client):
    r = client.post('/api/upload/confirm', json={'token': 'a' * 32})
    assert r.status_code == 404


def test_cancel_is_idempotent(client, png_bytes):
    token = stage_file(client, 'c.png', png_bytes).get_json()['token']
    assert client.post('/api/upload/cancel', json={'token': token}).status_code == 200
    # Cancelling again is still a 200 (best-effort).
    assert client.post('/api/upload/cancel', json={'token': token}).status_code == 200


def test_ico_preview_is_null(client):
    # .ico is allowed but not a Pillow-thumbnail format and not svg -> no preview.
    r = stage_file(client, 'favicon.ico', b'\x00\x00\x01\x00')
    assert r.status_code == 200
    assert r.get_json()['preview'] is None
