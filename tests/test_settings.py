"""Settings endpoints: validation, port checks, and the local-only guard."""
import socket

import pytest

from config import Config


def test_get_settings_shape(client):
    body = client.get('/api/settings').get_json()
    for key in ('data_dir', 'port', 'staging_timeout', 'theme', 'allowed_origin_ports'):
        assert key in body


# ── Theme ────────────────────────────────────────

@pytest.mark.parametrize('theme,code', [
    ('auto', 200), ('light', 200), ('dark', 200), ('neon', 400), ('', 400),
])
def test_theme_validation(client, theme, code):
    assert client.put('/api/settings/theme', json={'theme': theme}).status_code == code


# ── Staging timeout ──────────────────────────────

@pytest.mark.parametrize('value,code', [
    (10, 200), (3600, 200), (300, 200),
    (9, 400), (3601, 400), ('abc', 400), (None, 400),
])
def test_staging_timeout_validation(client, value, code):
    assert client.put('/api/settings/staging-timeout',
                      json={'staging_timeout': value}).status_code == code


# ── Port ─────────────────────────────────────────

@pytest.mark.parametrize('port,code', [
    (1023, 400), (65536, 400), ('nope', 400), (None, 400),
])
def test_port_range_validation(client, port, code):
    assert client.put('/api/settings/port', json={'port': port}).status_code == code


def test_port_same_as_current_rejected(client):
    r = client.put('/api/settings/port', json={'port': Config.PORT})
    assert r.status_code == 400


def test_port_in_use_rejected(client):
    # Hold an ephemeral port on 0.0.0.0 so is_port_available() reports it busy.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', 0))
    busy_port = s.getsockname()[1]
    try:
        if busy_port == Config.PORT:  # avoid the "same port" branch
            pytest.skip('ephemeral port collided with current port')
        r = client.put('/api/settings/port', json={'port': busy_port})
        assert r.status_code == 400
        assert 'in use' in r.get_json()['error'].lower()
    finally:
        s.close()


def test_port_valid_saved(client):
    # Find a currently-free port, then save it (save only writes settings.json).
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', 0))
    free_port = s.getsockname()[1]
    s.close()
    if free_port == Config.PORT:
        pytest.skip('ephemeral port collided with current port')
    r = client.put('/api/settings/port', json={'port': free_port})
    assert r.status_code == 200 and r.get_json()['saved_port'] == free_port


# ── data-dir ─────────────────────────────────────

def test_data_dir_missing_path(client):
    assert client.put('/api/settings/data-dir', json={}).status_code == 400


def test_data_dir_same_as_current(client):
    r = client.put('/api/settings/data-dir', json={'data_dir': str(Config.DATA_DIR)})
    assert r.status_code == 400


def test_data_dir_nonexistent_parent(client):
    r = client.put('/api/settings/data-dir',
                   json={'data_dir': '/no/such/parent/here/child'})
    assert r.status_code == 400


# ── allowed-ports ────────────────────────────────

def test_allowed_ports_dedup(client):
    r = client.put('/api/settings/allowed-ports',
                   json={'allowed_origin_ports': [3000, 3000, 8080]})
    assert r.status_code == 200
    assert r.get_json()['allowed_origin_ports'] == [3000, 8080]


# ── Local-only guard (parametrized) ──────────────

@pytest.mark.parametrize('method,path,payload', [
    ('post', '/api/shutdown', None),
    ('post', '/api/settings/browse', None),
    ('put', '/api/settings/data-dir', {'data_dir': 'x'}),
    ('put', '/api/settings/port', {'port': 5000}),
    ('put', '/api/settings/allowed-ports', {'allowed_origin_ports': []}),
    ('delete', '/api/groups/whatever', None),
])
def test_admin_endpoints_blocked_from_lan(client, method, path, payload):
    fn = getattr(client, method)
    kwargs = {'environ_overrides': {'REMOTE_ADDR': '10.0.0.7'}}
    if payload is not None:
        kwargs['json'] = payload
    assert fn(path, **kwargs).status_code == 403
