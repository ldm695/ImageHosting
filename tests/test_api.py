"""End-to-end API tests covering groups, uploads, tags, staging, migration,
CORS, the local-only guard, and SVG hardening."""
import io
import json

from conftest import upload_png
from config import Config


# ── Health ───────────────────────────────────────

def test_status(client):
    r = client.get('/api/status')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'running'


# ── Groups ───────────────────────────────────────

def test_create_list_delete_group(client):
    assert client.post('/api/groups', json={'name': 'photos'}).status_code == 201
    names = [g['name'] for g in client.get('/api/groups').get_json()]
    assert 'photos' in names
    # duplicate
    assert client.post('/api/groups', json={'name': 'photos'}).status_code == 409
    # delete
    assert client.delete('/api/groups/photos').status_code == 200


def test_invalid_group_name_rejected(client):
    assert client.post('/api/groups', json={'name': 'bad name!'}).status_code == 400
    assert client.post('/api/groups', json={'name': '../escape'}).status_code == 400


def test_cannot_delete_default_group(client):
    r = client.delete(f'/api/groups/{Config.DEFAULT_GROUP}')
    assert r.status_code == 400


# ── Upload ───────────────────────────────────────

def test_upload_and_scan(client):
    r = upload_png(client, 'pic.png')
    assert r.status_code == 200
    body = r.get_json()
    assert len(body['uploaded']) == 1
    info = body['uploaded'][0]
    assert info['thumbnail_url'].endswith('/thumbnails/general/pic.png')
    assert info['width'] == 10 and info['height'] == 10

    images = client.get('/api/images').get_json()['images']
    assert any(i['filename'] == 'pic.png' for i in images)


def test_upload_unsafe_filename_rejected(client):
    r = upload_png(client, '../evil.png')
    body = r.get_json()
    assert body['uploaded'] == []
    assert body['errors'] and 'unsafe' in body['errors'][0]['error'].lower()


def test_upload_duplicate_rejected(client):
    upload_png(client, 'dup.png')
    r = upload_png(client, 'dup.png')
    assert r.get_json()['errors'][0]['error'].lower().find('exist') != -1


# ── Tags ─────────────────────────────────────────

def test_tag_set_and_remove(client):
    upload_png(client, 'tagged.png')
    r = client.put('/api/image/tagged.png/tag', json={'tag': 'holiday'})
    assert r.status_code == 200 and r.get_json()['tag'] == 'holiday'
    imgs = client.get('/api/images?tag=holiday').get_json()['images']
    assert len(imgs) == 1
    assert client.delete('/api/image/tagged.png/tag').status_code == 200
    assert client.get('/api/images?tag=holiday').get_json()['images'] == []


def test_tag_rename_and_delete_global(client):
    upload_png(client, 'a.png', tag='x')
    upload_png(client, 'b.png', tag='x')
    r = client.put('/api/tags/x', json={'new_tag': 'y'})
    assert r.get_json()['updated'] == 2
    r = client.delete('/api/tags/y')
    assert r.get_json()['removed'] == 2


def test_invalid_tag_rejected(client):
    upload_png(client, 'c.png')
    r = client.put('/api/image/c.png/tag', json={'tag': 'bad*tag'})
    assert r.status_code == 400


# ── Dimension cache (#6) ─────────────────────────

def test_dims_cache_written(client):
    upload_png(client, 'dim.png')
    client.get('/api/images')  # triggers scan_images -> writes cache
    dims_file = Config.UPLOAD_DIR / Config.DEFAULT_GROUP / '.dims.json'
    assert dims_file.exists()
    data = json.loads(dims_file.read_text(encoding='utf-8'))
    assert data['dim.png']['w'] == 10 and data['dim.png']['h'] == 10


# ── Staging ──────────────────────────────────────

def _stage(client, name, png_bytes):
    return client.post(
        '/api/upload/stage',
        data={'files': (io.BytesIO(png_bytes), name)},
        content_type='multipart/form-data',
    )


def test_staging_stage_and_confirm(client, png_bytes):
    r = _stage(client, 'staged.png', png_bytes)
    assert r.status_code == 200
    token = r.get_json()['token']
    r = client.post('/api/upload/confirm', json={'token': token})
    assert r.status_code == 200 and r.get_json()['filename'] == 'staged.png'
    assert (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / 'staged.png').exists()


def test_staging_cancel_then_confirm_is_404(client, png_bytes):
    token = _stage(client, 's2.png', png_bytes).get_json()['token']
    assert client.post('/api/upload/cancel', json={'token': token}).status_code == 200
    r = client.post('/api/upload/confirm', json={'token': token})
    assert r.status_code == 404


def test_staging_bad_token_format(client):
    r = client.post('/api/upload/confirm', json={'token': 'nothex'})
    assert r.status_code == 400


# ── Migration (#1 local guard + dims/tags sidecars) ──

def test_migration_moves_images_and_sidecars(client, tmp_path):
    upload_png(client, 'm.png', tag='keep')
    client.get('/api/images')  # create .dims.json cache
    new_dir = tmp_path / 'moved'
    r = client.put('/api/settings/data-dir', json={'data_dir': str(new_dir)})
    assert r.status_code == 200
    assert (new_dir / 'uploads' / Config.DEFAULT_GROUP / 'm.png').exists()
    tags = json.loads((new_dir / 'uploads' / Config.DEFAULT_GROUP / '.tags.json').read_text('utf-8'))
    assert tags['m.png'] == 'keep'


# ── Local-only guard (#1) ────────────────────────

def test_admin_endpoint_blocked_from_lan(client):
    r = client.post('/api/shutdown', environ_overrides={'REMOTE_ADDR': '192.168.1.42'})
    assert r.status_code == 403


def test_admin_endpoint_allowed_from_loopback(client):
    # test_client defaults REMOTE_ADDR to 127.0.0.1
    r = client.put('/api/settings/allowed-ports', json={'allowed_origin_ports': [3000]})
    assert r.status_code == 200


# ── CORS (#allowlist) ────────────────────────────

def test_cors_allowed_origin_echoed(client):
    client.put('/api/settings/allowed-ports', json={'allowed_origin_ports': [3000]})
    r = client.get('/api/status', headers={'Origin': 'http://localhost:3000'})
    assert r.headers.get('Access-Control-Allow-Origin') == 'http://localhost:3000'


def test_cors_disallowed_origin_absent(client):
    client.put('/api/settings/allowed-ports', json={'allowed_origin_ports': [3000]})
    r = client.get('/api/status', headers={'Origin': 'http://localhost:9999'})
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_allowed_ports_validation(client):
    r = client.put('/api/settings/allowed-ports', json={'allowed_origin_ports': [99999]})
    assert r.status_code == 400
    r = client.put('/api/settings/allowed-ports', json={'allowed_origin_ports': 'nope'})
    assert r.status_code == 400


# ── SVG hardening (#2) ───────────────────────────

def test_svg_served_with_csp_sandbox(client):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / 'x.svg').write_bytes(svg)
    r = client.get('/uploads/general/x.svg')
    assert r.status_code == 200
    assert 'sandbox' in r.headers.get('Content-Security-Policy', '')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
