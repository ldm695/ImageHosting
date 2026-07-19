"""Image operations: rename, move, batch, per-file tags, non-Pillow formats."""

from conftest import make_png, upload_png

from config import Config

# ── Rename ───────────────────────────────────────


def test_rename_success(client):
    upload_png(client, "old.png")
    r = client.put("/api/image/old.png/rename", json={"new_name": "new.png"})
    assert r.status_code == 200 and r.get_json()["filename"] == "new.png"
    assert (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / "new.png").exists()
    assert not (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / "old.png").exists()


def test_rename_extension_must_match(client):
    upload_png(client, "a.png")
    r = client.put("/api/image/a.png/rename", json={"new_name": "a.jpg"})
    assert r.status_code == 400


def test_rename_conflict(client):
    upload_png(client, "a.png")
    upload_png(client, "b.png")
    r = client.put("/api/image/a.png/rename", json={"new_name": "b.png"})
    assert r.status_code == 409


def test_rename_not_found(client):
    r = client.put("/api/image/ghost.png/rename", json={"new_name": "x.png"})
    assert r.status_code == 404


def test_rename_moves_tag(client):
    upload_png(client, "a.png", tag="keep")
    client.put("/api/image/a.png/rename", json={"new_name": "b.png"})
    imgs = client.get("/api/images?tag=keep").get_json()["images"]
    assert [i["filename"] for i in imgs] == ["b.png"]


# ── Move (single) ────────────────────────────────


def test_move_success_with_thumb_and_tag(client):
    client.post("/api/groups", json={"name": "dest"})
    upload_png(client, "m.png", tag="t")
    r = client.put("/api/image/m.png/move", json={"to_group": "dest"})
    assert r.status_code == 200
    assert (Config.UPLOAD_DIR / "dest" / "m.png").exists()
    assert (Config.THUMBNAIL_DIR / "dest" / "m.png").exists()
    # Tag followed the file.
    imgs = client.get("/api/images?group=dest&tag=t").get_json()["images"]
    assert [i["filename"] for i in imgs] == ["m.png"]


def test_move_same_group_rejected(client):
    upload_png(client, "m.png")
    r = client.put("/api/image/m.png/move", json={"to_group": Config.DEFAULT_GROUP})
    assert r.status_code == 400


def test_move_not_found(client):
    client.post("/api/groups", json={"name": "dest"})
    r = client.put("/api/image/ghost.png/move", json={"to_group": "dest"})
    assert r.status_code == 404


def test_move_conflict(client):
    client.post("/api/groups", json={"name": "dest"})
    upload_png(client, "m.png")
    upload_png(client, "m.png", group="dest")
    r = client.put("/api/image/m.png/move", json={"to_group": "dest"})
    assert r.status_code == 409


# ── Batch ────────────────────────────────────────


def test_batch_move(client):
    client.post("/api/groups", json={"name": "dest"})
    upload_png(client, "a.png")
    upload_png(client, "b.png")
    r = client.post(
        "/api/images/batch-move",
        json={
            "group": Config.DEFAULT_GROUP,
            "to_group": "dest",
            "files": ["a.png", "b.png", "ghost.png"],
        },
    )
    body = r.get_json()
    assert set(body["moved"]) == {"a.png", "b.png"}
    assert len(body["errors"]) == 1


def test_batch_tag(client):
    upload_png(client, "a.png")
    upload_png(client, "b.png")
    r = client.post(
        "/api/images/batch-tag",
        json={"group": Config.DEFAULT_GROUP, "tag": "batch", "files": ["a.png", "b.png"]},
    )
    assert set(r.get_json()["tagged"]) == {"a.png", "b.png"}
    imgs = client.get("/api/images?tag=batch").get_json()["images"]
    assert len(imgs) == 2


def test_batch_delete(client):
    upload_png(client, "a.png")
    r = client.post(
        "/api/images/batch-delete", json={"group": Config.DEFAULT_GROUP, "files": ["a.png"]}
    )
    assert r.get_json()["deleted"] == ["a.png"]
    assert not (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / "a.png").exists()


# ── Per-file tags on upload ──────────────────────


def test_upload_per_file_tags(client):
    import io
    import json

    files = [(io.BytesIO(make_png()), "a.png"), (io.BytesIO(make_png()), "b.png")]
    r = client.post(
        "/api/upload",
        data={"files": files, "tags": json.dumps(["one", "two"])},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    got = {i["filename"]: i.get("tag") for i in r.get_json()["uploaded"]}
    assert got == {"a.png": "one", "b.png": "two"}


# ── Non-Pillow formats ───────────────────────────


def test_upload_svg_no_dimensions(client):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="5" height="5"></svg>'
    r = client.post(
        "/api/upload",
        data={"files": (__import__("io").BytesIO(svg), "v.svg")},
        content_type="multipart/form-data",
    )
    info = r.get_json()["uploaded"][0]
    assert "width" not in info and "height" not in info
    assert info["thumbnail_url"].endswith("/thumbnails/general/v.svg")


# ── Static serving fallback ──────────────────────


def test_thumbnail_falls_back_to_original(client):
    # SVG has no generated thumbnail, so /thumbnails/... serves the original.
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    (Config.UPLOAD_DIR / Config.DEFAULT_GROUP / "v.svg").write_bytes(svg)
    r = client.get("/thumbnails/general/v.svg")
    assert r.status_code == 200
    assert svg in r.data
