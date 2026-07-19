"""Unit tests for pure helpers in utils.py and helpers.py."""

import pytest

import app as app_module
import helpers
import utils
from config import Config

# ── validate_tag ─────────────────────────────────


@pytest.mark.parametrize(
    "tag,ok",
    [
        ("holiday", True),
        ("my tag_1-2", True),
        ("  spaced  ", True),  # stripped, still valid
        ("", False),
        ("   ", False),
        ("bad*char", False),
        ("emoji😀", False),
        ("x" * 64, True),
        ("x" * 65, False),
    ],
)
def test_validate_tag(tag, ok):
    result, _ = utils.validate_tag(tag)
    assert result is ok


# ── is_valid_group_name ──────────────────────────


@pytest.mark.parametrize(
    "name,ok",
    [
        ("general", True),
        ("My_Group-1", True),
        ("", False),
        ("has space", False),
        ("../escape", False),
        ("dot.name", False),
        ("a" * 64, True),
        ("a" * 65, False),
    ],
)
def test_is_valid_group_name(name, ok):
    assert utils.is_valid_group_name(name) is ok


# ── format_size ──────────────────────────────────


@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024**3, "1.0 GB"),
    ],
)
def test_format_size(size, expected):
    assert utils.format_size(size) == expected


# ── allowed_file ─────────────────────────────────


@pytest.mark.parametrize(
    "name,ok",
    [
        ("a.png", True),
        ("a.PNG", True),  # case-insensitive
        ("a.jpeg", True),
        ("a.svg", True),
        ("a.txt", False),
        ("noext", False),
        ("a.exe", False),
    ],
)
def test_allowed_file(name, ok):
    assert utils.allowed_file(name) is ok


# ── atomic_write_text ────────────────────────────


def test_atomic_write_creates_and_overwrites(tmp_path):
    target = tmp_path / "x.json"
    utils.atomic_write_text(target, "first")
    assert target.read_text(encoding="utf-8") == "first"
    utils.atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"
    # No leftover temp files in the directory.
    assert list(tmp_path.glob("*.tmp")) == []


# ── Dimension cache ──────────────────────────────


def test_dims_roundtrip_and_removal():
    group = Config.DEFAULT_GROUP
    assert utils.load_dims(group) == {}
    utils.write_dims(group, {"a.png": {"w": 4, "h": 5, "size": 99}})
    loaded = utils.load_dims(group)
    assert loaded["a.png"]["w"] == 4 and loaded["a.png"]["size"] == 99
    # Writing empty removes the file.
    utils.write_dims(group, {})
    assert not (Config.UPLOAD_DIR / group / ".dims.json").exists()


# ── Tag storage (with lock) ──────────────────────


def test_tag_storage_crud():
    g = Config.DEFAULT_GROUP
    utils.save_tag(g, "a.png", "red")
    utils.save_tag(g, "b.png", "red")
    assert utils.load_tags(g) == {"a.png": "red", "b.png": "red"}
    assert utils.rename_tag_global(g, "red", "blue") == 2
    assert set(utils.load_tags(g).values()) == {"blue"}
    utils.rename_tag_entry(g, "a.png", "a2.png")
    assert "a2.png" in utils.load_tags(g)
    assert utils.delete_tag_global(g, "blue") == 2
    # Empty map removes the file.
    assert not (Config.UPLOAD_DIR / g / ".tags.json").exists()


# ── Shared format map (#9) ───────────────────────


def test_thumbnail_format_map_shared():
    import staging

    assert staging.THUMBNAIL_FORMAT_MAP is utils.THUMBNAIL_FORMAT_MAP
    assert utils.THUMBNAIL_FORMAT_MAP[".jpg"] == "JPEG"


# ── helpers (need a request context for jsonify) ─


def test_group_error():
    with app_module.app.test_request_context():
        assert helpers.group_error("ok-name") is None
        resp, code = helpers.group_error("../bad")
        assert code == 400


def test_safe_or_error():
    with app_module.app.test_request_context():
        safe, err = helpers.safe_or_error("clean.png")
        assert safe == "clean.png" and err is None
        safe, err = helpers.safe_or_error("../../etc/passwd")
        # secure_filename strips to 'etc_passwd' (non-empty), so this is accepted;
        # a name that sanitizes to empty is what triggers the error.
        assert safe and err is None
        safe, err = helpers.safe_or_error("...")
        assert safe is None and err is not None
