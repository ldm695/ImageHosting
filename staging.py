"""
Staging (upload confirmation) for ImageHosting.

Manages the staging area where uploaded files wait for confirmation.
Provides three API endpoints: stage, confirm, cancel.
"""

import base64
import io
import json
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import jsonify, request, url_for
from werkzeug.utils import secure_filename

from app import app  # Flask instance for route registration
from config import Config
from utils import (
    THUMBNAIL_FORMAT_MAP,
    allowed_file,
    atomic_write_text,
    ensure_group_dirs,
    generate_thumbnail,
    get_image_info,
    is_valid_group_name,
    save_tag,
    validate_tag,
)

# ── State ────────────────────────────────────────

_staging_timers: dict[str, threading.Timer] = {}
_staging_lock = threading.Lock()


# ── Helpers ──────────────────────────────────────


class _StagingMeta:
    """Internal metadata for a staged file."""

    __slots__ = ("safe_name", "original_name", "group", "created_at", "tag")

    def __init__(self, safe_name: str, original_name: str, group: str, tag: str = ""):
        self.safe_name = safe_name
        self.original_name = original_name
        self.group = group
        self.tag = tag or ""
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "safe_name": self.safe_name,
            "original_name": self.original_name,
            "group": self.group,
            "tag": self.tag,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "_StagingMeta":
        m = _StagingMeta(d["safe_name"], d["original_name"], d["group"], d.get("tag", ""))
        m.created_at = d.get("created_at", "")
        return m


def _remove_staged(token: str):
    """Remove a staged file and its metadata (best-effort)."""
    meta_path = Config.STAGING_DIR / f"{token}.meta.json"
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        staged_file = Config.STAGING_DIR / f"{token}_{meta['safe_name']}"
        staged_file.unlink(missing_ok=True)
        meta_path.unlink()
    except Exception:
        pass


def _staging_cleanup(token: str):
    """Auto-cleanup on timeout — remove staged file and metadata.

    Only removes if this call successfully claims the timer. If confirm/cancel
    already popped it, they own the token and we must not delete their file.
    """
    with _staging_lock:
        timer = _staging_timers.pop(token, None)
    if timer is None:
        return
    _remove_staged(token)


def cleanup_all_staging():
    """Clean up any leftover staged files (call at startup)."""
    staging_dir = Config.STAGING_DIR
    if not staging_dir.exists():
        return
    for f in staging_dir.iterdir():
        try:
            if f.is_file():
                f.unlink()
        except Exception:
            pass


# ── Preview ──────────────────────────────────────


def _generate_preview(file_path: Path) -> str | None:
    """Generate a base64 data URL preview thumbnail for a staged image."""
    ext = file_path.suffix.lower()
    try:
        if ext in Config.PILLOW_FORMATS:
            from PIL import Image

            with Image.open(file_path) as src:
                img: Image.Image = src
                img.thumbnail((256, 256))
                buf = io.BytesIO()
                # Determine output format. BMP is re-encoded as PNG for a
                # compact data URL; everything else follows the shared map.
                out_fmt = "PNG" if ext == ".bmp" else THUMBNAIL_FORMAT_MAP.get(ext, "JPEG")
                mime = f"image/{out_fmt.lower()}"
                # Convert to RGB for JPEG
                if out_fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                img.save(buf, format=out_fmt, quality=70)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:{mime};base64,{b64}"
        elif ext == ".svg":
            svg_text = file_path.read_text(encoding="utf-8")
            b64 = base64.b64encode(svg_text.encode("utf-8")).decode("ascii")
            return f"data:image/svg+xml;base64,{b64}"
    except Exception:
        pass
    return None


# ── Routes ───────────────────────────────────────


@app.route("/api/upload/stage", methods=["POST"])
def api_upload_stage():
    """Upload a file to staging area. Requires a subsequent confirm to finalize."""
    group = request.args.get("group", Config.DEFAULT_GROUP)
    if not is_valid_group_name(group):
        return jsonify({"error": "Invalid group name"}), 400
    ensure_group_dirs(group)

    if "files" not in request.files:
        return jsonify({"error": "No file data in request"}), 400

    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename and f.filename.strip()]

    if not files:
        return jsonify({"error": "Please select files to upload"}), 400

    # Only process the first file (single-file staging)
    file = files[0]

    if not allowed_file(file.filename):
        return jsonify(
            {
                "error": (
                    f"Unsupported format. Allowed: {', '.join(sorted(Config.ALLOWED_EXTENSIONS))}"
                )
            }
        ), 400

    # Optional preset tag (query arg or form field) — applied on confirm
    tag = (request.args.get("tag") or request.form.get("tag") or "").strip()
    if tag:
        ok, err = validate_tag(tag)
        if not ok:
            return jsonify({"error": err}), 400

    # Anti-abuse: check staging count
    with _staging_lock:
        if len(_staging_timers) >= Config.STAGING_MAX_FILES:
            return jsonify(
                {"error": "Too many pending uploads. Confirm or cancel existing ones first."}
            ), 429

    # Validate filename (reject unsafe characters, no auto-sanitize)
    safe = secure_filename(file.filename)
    if not safe or safe != file.filename:
        return jsonify(
            {
                "error": (
                    "Filename contains invalid or unsafe characters. Use only "
                    "letters, numbers, dots, underscores, and hyphens."
                )
            }
        ), 400

    # Check name conflict before staging (group dirs already ensured above)
    if (Config.UPLOAD_DIR / group / safe).exists():
        return jsonify(
            {
                "error": f'File "{safe}" already exists in group "{group}"',
                "filename": safe,
                "group": group,
            }
        ), 409

    # Stage it
    token = uuid.uuid4().hex
    staged_name = f"{token}_{safe}"
    staged_path = Config.STAGING_DIR / staged_name

    try:
        file.save(str(staged_path))
    except Exception as e:
        return jsonify({"error": f"Save failed: {str(e)}"}), 500

    # Write metadata
    meta = _StagingMeta(safe, file.filename, group, tag)
    meta_path = Config.STAGING_DIR / f"{token}.meta.json"
    try:
        atomic_write_text(meta_path, json.dumps(meta.to_dict(), ensure_ascii=False))
    except Exception as e:
        staged_path.unlink(missing_ok=True)
        return jsonify({"error": f"Metadata write failed: {str(e)}"}), 500

    # Schedule auto-cleanup
    timer = threading.Timer(Config.STAGING_TIMEOUT, _staging_cleanup, args=[token])
    timer.daemon = True
    with _staging_lock:
        _staging_timers[token] = timer
    timer.start()

    # Generate preview thumbnail
    preview = _generate_preview(staged_path)

    return jsonify(
        {
            "token": token,
            "filename": safe,
            "original_name": file.filename,
            "group": group,
            "tag": tag,
            "expires_in": Config.STAGING_TIMEOUT,
            "url": url_for("serve_upload", group=group, filename=safe),
            "absolute_path": str((Config.UPLOAD_DIR / group / safe).resolve()),
            "preview": preview,
        }
    )


@app.route("/api/upload/confirm", methods=["POST"])
def api_upload_confirm():
    """Confirm a staged upload — move from staging to final location."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token", "") or "").strip()

    if not token:
        return jsonify({"error": "Token is required"}), 400

    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return jsonify({"error": "Invalid token format"}), 400

    meta_path = Config.STAGING_DIR / f"{token}.meta.json"
    if not meta_path.exists():
        return jsonify({"error": "Token not found or expired"}), 404

    try:
        meta = _StagingMeta.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
    except Exception:
        return jsonify({"error": "Failed to read staging metadata"}), 500

    # Determine target group (request overrides original)
    group = data.get("group", meta.group)
    if not is_valid_group_name(group):
        return jsonify({"error": "Invalid group name"}), 400

    # Determine tag: request body overrides the staged preset. An explicit
    # empty string clears the preset; omitting the field keeps it.
    if "tag" in data:
        tag = (data.get("tag") or "").strip()
    else:
        tag = meta.tag
    if tag:
        ok, err = validate_tag(tag)
        if not ok:
            return jsonify({"error": err}), 400

    # Claim the token: whoever pops the timer owns it. If it's already gone,
    # a concurrent auto-cleanup (timeout) or cancel got there first, so the
    # staged file may already be deleted — treat it as expired.
    with _staging_lock:
        timer = _staging_timers.pop(token, None)
    if timer is None:
        return jsonify({"error": "Token not found or expired"}), 404
    timer.cancel()

    staged_file = Config.STAGING_DIR / f"{token}_{meta.safe_name}"
    if not staged_file.exists():
        return jsonify({"error": "Staged file not found"}), 404

    ensure_group_dirs(group)
    dest_path = Config.UPLOAD_DIR / group / meta.safe_name

    try:
        shutil.move(str(staged_file), str(dest_path))
    except Exception as e:
        return jsonify({"error": f"Move failed: {str(e)}"}), 500

    # Clean up metadata
    try:
        meta_path.unlink()
    except Exception:
        pass

    # Generate thumbnail
    ext = dest_path.suffix.lower()
    if ext in Config.PILLOW_FORMATS:
        thumbpath = Config.THUMBNAIL_DIR / group / dest_path.name
        generate_thumbnail(dest_path, thumbpath)

    # Apply preset/override tag
    if tag:
        save_tag(group, dest_path.name, tag)

    info = get_image_info(dest_path.name, group)
    payload = {"success": True, "filename": dest_path.name, "group": group}
    if info:
        payload.update(info)

    return jsonify(payload)


@app.route("/api/upload/cancel", methods=["POST"])
def api_upload_cancel():
    """Cancel a staged upload — remove staged file and metadata."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token", "") or "").strip()

    if not token:
        return jsonify({"error": "Token is required"}), 400

    if not re.fullmatch(r"[0-9a-f]{32}", token):
        return jsonify({"error": "Invalid token format"}), 400

    # Cancel timer
    with _staging_lock:
        timer = _staging_timers.pop(token, None)
    if timer:
        timer.cancel()

    # Remove staged file
    _remove_staged(token)

    return jsonify({"success": True})
