"""
ImageHosting — Local image hosting service
===========================================
Single-user LAN image hosting with Groups / Upload / Browse / Delete / Copy links / Thumbnails
"""

import argparse
import json
import mimetypes
import shutil
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from config import Config
from helpers import local_only

# ── Settings persistence ─────────────────────────

SETTINGS_FILE = Config.DATA_DIR / "settings.json"

# Serializes storage-directory migration and the runtime Config switch so two
# concurrent migrations can't interleave and corrupt the move.
_migration_lock = threading.Lock()


def load_settings() -> dict:
    """Load settings from settings.json"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(data: dict):
    """Save settings to settings.json (merges with existing)"""
    current = load_settings()
    current.update(data)
    # atomic_write_text is imported below (after this def); resolved at call
    # time, and all save_settings calls happen after that import runs.
    atomic_write_text(
        SETTINGS_FILE,
        json.dumps(current, indent=2, ensure_ascii=False),
    )


# ── App Init ─────────────────────────────────────

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _has_cli_arg(flag: str) -> bool:
    """True if the given CLI flag was passed (so it overrides settings.json)."""
    return any(a.startswith(flag) for a in sys.argv[1:])


def _apply_persisted_settings(persisted: dict):
    """Apply values loaded from settings.json onto Config at startup."""
    # data_dir and port honor CLI overrides, so they stay explicit.
    if "data_dir" in persisted and not _has_cli_arg("--data-dir"):
        Config.DATA_DIR = Path(persisted["data_dir"])
        Config.UPLOAD_DIR = Config.DATA_DIR / "uploads"
        Config.THUMBNAIL_DIR = Config.DATA_DIR / "thumbnails"
    if "port" in persisted and not _has_cli_arg("--port"):
        Config.PORT = int(persisted["port"])

    # Simple persisted scalars: (settings key, Config attr, coercion).
    for key, attr, coerce in (
        ("staging_timeout", "STAGING_TIMEOUT", int),
        ("theme", "THEME", str),
        (
            "allowed_origin_ports",
            "ALLOWED_ORIGIN_PORTS",
            lambda v: [int(p) for p in v] if isinstance(v, list) else Config.ALLOWED_ORIGIN_PORTS,
        ),
    ):
        if key in persisted:
            setattr(Config, attr, coerce(persisted[key]))


# Apply persisted settings
_apply_persisted_settings(load_settings())

# Ensure root dirs exist
Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Config.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
# Ensure default group dirs exist
(Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
(Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
# Ensure staging dir exists and clean leftover files from last run
Config.STAGING_DIR.mkdir(parents=True, exist_ok=True)

# Register MIME types
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("font/woff2", ".woff2")

# ── Utilities ────────────────────────────────────

from utils import (  # noqa: E402
    allowed_file,
    atomic_write_text,
    get_local_ip,
    is_port_available,
)

# ── Dynamic CORS ─────────────────────────────────
# Cross-origin requests are allowed only from the configured port allowlist.
# The check runs per-request (reads Config live), so updating the allowlist
# via /api/settings/allowed-ports takes effect immediately — no restart.

_LOCAL_IP = get_local_ip()


def _allowed_origins() -> set:
    """Build the set of permitted Origin values from the port allowlist."""
    hosts = {"localhost", "127.0.0.1"}
    if _LOCAL_IP:
        hosts.add(_LOCAL_IP)
    origins = set()
    for port in Config.ALLOWED_ORIGIN_PORTS:
        for host in hosts:
            origins.add(f"http://{host}:{port}")
            origins.add(f"https://{host}:{port}")
    return origins


@app.after_request
def _apply_cors(resp):
    origin = request.headers.get("Origin")
    if origin and origin in _allowed_origins():
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers.setdefault("Vary", "Origin")
    return resp


# ── Staging (upload confirmation) ─────────────────

# Register this module as 'app' so staging.py's 'from app import app' works
sys.modules["app"] = sys.modules[__name__]

import staging  # noqa: F811, E402

# cleanup_all_staging() is called in main() after all imports
# Register domain route blueprints (groups, images/tags/batch). File serving,
# settings, system, and the page route stay in this module.
from routes import register_blueprints  # noqa: E402

register_blueprints(app)

_http_server = None  # Set by make_server in _serve_forever()

# ── Page Routes ─────────────────────────────────


def _render_index():
    """Render the single-page app shell (shared by / and the SPA 404 fallback)."""
    return render_template(
        "index.html",
        title=Config.SITE_TITLE,
        port=Config.PORT,
        local_ip=_LOCAL_IP,
        max_size_mb=Config.MAX_CONTENT_LENGTH // (1024 * 1024),
        default_group=Config.DEFAULT_GROUP,
        data_dir=str(Config.DATA_DIR),
        theme=getattr(Config, "THEME", "auto"),
    )


@app.route("/")
def index():
    """Main page"""
    return _render_index()


# ── Settings API ─────────────────────────────────


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Get current settings"""
    return jsonify(
        {
            "data_dir": str(Config.DATA_DIR),
            "port": Config.PORT,
            "staging_timeout": Config.STAGING_TIMEOUT,
            "theme": getattr(Config, "THEME", "auto"),
            "allowed_origin_ports": Config.ALLOWED_ORIGIN_PORTS,
        }
    )


# Serializes native folder-picker dialogs. Tk is not thread-safe and only one
# dialog should ever be open at a time.
_browse_lock = threading.Lock()


def _pick_folder() -> dict:
    """Run the tkinter folder dialog in its own thread.

    In tray mode Flask serves from a background thread while the main thread
    is owned by the tray loop; creating/using Tk on a dedicated short-lived
    thread keeps every Tk call on one thread and off the request/tray threads.
    Returns {'path': str|None} or {'error': str, 'status': int}.
    """
    result: dict = {}

    def _run():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(title="Select Image Storage Directory")
            root.destroy()
            result["path"] = folder or None
        except ImportError:
            result["error"] = "tkinter not available on this system"
            result["status"] = 501
        except Exception as e:
            result["error"] = f"Failed to open folder picker: {str(e)}"
            result["status"] = 500

    t = threading.Thread(target=_run)
    t.start()
    t.join()
    return result


@app.route("/api/settings/browse", methods=["POST"])
@local_only
def api_browse_folder():
    """Open native folder-picker dialog via tkinter, return selected path."""
    if not _browse_lock.acquire(blocking=False):
        return jsonify({"error": "A folder picker is already open"}), 409
    try:
        result = _pick_folder()
    finally:
        _browse_lock.release()

    if "error" in result:
        return jsonify({"error": result["error"]}), result.get("status", 500)
    if result.get("path"):
        return jsonify({"path": result["path"]})
    return jsonify({"path": None, "error": "No folder selected"}), 400


@app.route("/api/settings/data-dir", methods=["PUT"])
@local_only
def api_update_data_dir():
    """Update storage directory with file migration."""
    data = request.get_json(silent=True) or {}
    new_dir = (data.get("data_dir", "") or "").strip()

    if not new_dir:
        return jsonify({"error": "Directory path is required"}), 400

    new_root = Path(new_dir).resolve()
    old_root = Config.DATA_DIR.resolve()

    if new_root == old_root:
        return jsonify({"error": "New directory is the same as the current one"}), 400
    if not new_root.parent.exists():
        return jsonify({"error": f'Parent directory "{new_root.parent}" does not exist'}), 400

    new_upload = new_root / "uploads"
    new_thumb = new_root / "thumbnails"

    try:
        new_upload.mkdir(parents=True, exist_ok=True)
        new_thumb.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = new_upload / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        return jsonify({"error": f"Cannot write to directory: {str(e)}"}), 400

    migration_log = {"moved_uploads": 0, "moved_thumbnails": 0, "groups": []}

    # Hold the lock across the whole migration + Config switch so a second
    # migration (or a restart-triggered switch) can't interleave with this one.
    with _migration_lock:
        try:
            # Migrate each group from old to new
            if Config.UPLOAD_DIR.exists():
                for group_dir in Config.UPLOAD_DIR.iterdir():
                    if not group_dir.is_dir():
                        continue
                    gname = group_dir.name

                    # Migrate original images
                    files = [f for f in group_dir.iterdir() if f.is_file() and allowed_file(f.name)]
                    if files:
                        dst_dir = new_upload / gname
                        dst_dir.mkdir(parents=True, exist_ok=True)
                        for f in files:
                            shutil.move(str(f), str(dst_dir / f.name))
                            migration_log["moved_uploads"] += 1

                    # Migrate sidecar files (tag map + dimension cache) so
                    # they follow their images and don't block old-dir cleanup.
                    for sidecar in (".tags.json", ".dims.json"):
                        sc = group_dir / sidecar
                        if sc.exists():
                            dst_dir = new_upload / gname
                            dst_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(sc), str(dst_dir / sidecar))

                    # Migrate thumbnails for this group
                    old_td = Config.THUMBNAIL_DIR / gname
                    if old_td.exists():
                        tfiles = [f for f in old_td.iterdir() if f.is_file()]
                        if tfiles:
                            new_td = new_thumb / gname
                            new_td.mkdir(parents=True, exist_ok=True)
                            for f in tfiles:
                                shutil.move(str(f), str(new_td / f.name))
                                migration_log["moved_thumbnails"] += 1

                    migration_log["groups"].append(gname)

            # Clean up old uploads/thumbnails dirs only (NOT parent)
            for p in [Config.THUMBNAIL_DIR, Config.UPLOAD_DIR]:
                if p.exists():
                    try:
                        for child in sorted(p.iterdir(), reverse=True):
                            if child.is_dir():
                                try:
                                    child.rmdir()
                                except OSError:
                                    pass
                        p.rmdir()
                    except OSError:
                        pass

        except Exception as e:
            migration_log["error"] = str(e)

        # Switch at runtime
        Config.DATA_DIR = new_root
        Config.UPLOAD_DIR = new_upload
        Config.THUMBNAIL_DIR = new_thumb

        # Ensure default group exists in new location
        (Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
        (Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)

        save_settings({"data_dir": str(new_root)})

    msg = "Storage directory updated instantly."
    if migration_log["moved_uploads"] > 0:
        msg += f" Migrated {migration_log['moved_uploads']} image(s)."
    if migration_log.get("error"):
        msg += f" Warning: partial migration - {migration_log['error']}"

    return jsonify(
        {
            "success": True,
            "message": msg,
            "data_dir": str(new_root),
            "migration": migration_log,
        }
    )


@app.route("/api/settings/staging-timeout", methods=["PUT"])
def api_update_staging_timeout():
    """Update staging timeout only."""
    data = request.get_json(silent=True) or {}
    new_timeout = data.get("staging_timeout")

    if new_timeout is None:
        return jsonify({"error": "staging_timeout is required"}), 400

    try:
        timeout = int(new_timeout)
        if timeout < 10 or timeout > 3600:
            return jsonify({"error": "Staging timeout must be between 10 and 3600 seconds"}), 400
        Config.STAGING_TIMEOUT = timeout
        save_settings({"staging_timeout": timeout})
        return jsonify({"success": True, "staging_timeout": timeout})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid timeout value"}), 400


@app.route("/api/settings/port", methods=["PUT"])
@local_only
def api_update_port():
    """Update server port with availability check and auto-restart."""
    data = request.get_json(silent=True) or {}
    new_port = data.get("port")

    if new_port is None:
        return jsonify({"error": "port is required"}), 400

    try:
        port = int(new_port)
        if port < 1024 or port > 65535:
            return jsonify({"error": "Port must be between 1024 and 65535"}), 400
        if port == Config.PORT:
            return jsonify({"error": "Port is the same as the current one"}), 400

        # Reject ports already bound by another process — the new port must be
        # free for the server to rebind to it on restart.
        if not is_port_available(port):
            return jsonify({"error": f"Port {port} is already in use"}), 400

        # Save to settings.json only — takes effect on next restart
        save_settings({"port": port})

        return jsonify({"success": True, "saved_port": port, "_applied_on_restart": True})
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid port value"}), 400


@app.route("/api/settings/allowed-ports", methods=["PUT"])
@local_only
def api_update_allowed_ports():
    """Update the CORS origin port allowlist. Applies immediately (no restart)."""
    data = request.get_json(silent=True) or {}
    ports = data.get("allowed_origin_ports")

    if not isinstance(ports, list):
        return jsonify({"error": "allowed_origin_ports must be a list"}), 400

    clean = []
    for p in ports:
        try:
            pi = int(p)
        except (ValueError, TypeError):
            return jsonify({"error": f"Invalid port: {p}"}), 400
        if pi < 1 or pi > 65535:
            return jsonify({"error": f"Port out of range: {pi}"}), 400
        if pi not in clean:
            clean.append(pi)

    Config.ALLOWED_ORIGIN_PORTS = clean
    save_settings({"allowed_origin_ports": clean})
    return jsonify({"success": True, "allowed_origin_ports": clean})


@app.route("/api/settings/theme", methods=["PUT"])
def api_update_theme():
    """Update theme preference (auto / light / dark)."""
    data = request.get_json(silent=True) or {}
    theme = (data.get("theme", "") or "").strip().lower()

    if theme not in ("auto", "light", "dark"):
        return jsonify({"error": "Theme must be auto, light, or dark"}), 400

    Config.THEME = theme
    save_settings({"theme": theme})
    return jsonify({"success": True, "theme": theme})


# ── Static File Routes ──────────────────────────


def _harden_image_response(resp, filename: str):
    """Add anti-XSS / anti-sniffing headers to a served image.

    SVGs can embed <script>; served with image/svg+xml they'd run in this
    origin if opened as a top-level document. `sandbox` (plus a locked-down
    default-src) disables scripts when the SVG is loaded as a document, while
    <img> embedding still renders. nosniff stops MIME confusion for all files.
    """
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if filename.lower().endswith(".svg"):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        )
    return resp


@app.route("/uploads/<group>/<filename>")
def serve_upload(group, filename):
    """Serve original image"""
    safe_group = secure_filename(group) or Config.DEFAULT_GROUP
    safe_file = secure_filename(filename)
    resp = send_from_directory(str(Config.UPLOAD_DIR / safe_group), safe_file)
    return _harden_image_response(resp, safe_file)


@app.route("/thumbnails/<group>/<filename>")
def serve_thumbnail(group, filename):
    """Serve thumbnail (fallback to original if missing)"""
    safe_group = secure_filename(group) or Config.DEFAULT_GROUP
    safe_file = secure_filename(filename)
    thumbpath = Config.THUMBNAIL_DIR / safe_group / safe_file
    if thumbpath.exists():
        resp = send_from_directory(str(Config.THUMBNAIL_DIR / safe_group), safe_file)
    else:
        resp = send_from_directory(str(Config.UPLOAD_DIR / safe_group), safe_file)
    return _harden_image_response(resp, safe_file)


# ── System API ──────────────────────────────────


@app.route("/api/shutdown", methods=["POST"])
@local_only
def api_shutdown():
    """Shut down the server (used by tray restart / Exit)."""
    # Apply pending port from settings.json so restart picks it up
    _pending = load_settings()
    if "port" in _pending:
        Config.PORT = int(_pending["port"])
    if _http_server is not None:
        srv = _http_server
        threading.Timer(0.5, lambda: srv.shutdown() if srv else None).start()
    return jsonify({"success": True})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Simple health-check endpoint (used by tray icon)"""
    return jsonify({"status": "running", "port": Config.PORT})


# ── Error Handlers ───────────────────────────────


@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify(
        {"error": f"File too large. Maximum: {Config.MAX_CONTENT_LENGTH // (1024 * 1024)} MB"}
    ), 413


@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Endpoint not found"}), 404
    return _render_index(), 404


# ── Entry ────────────────────────────────────────


def parse_args():
    is_frozen = getattr(sys, "frozen", False)
    parser = argparse.ArgumentParser(
        description="ImageHosting — Local image hosting service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  python app.py                          # Console mode\n"
        "  python app.py --tray                   # Tray icon mode\n"
        "  python app.py --port 8080              # Custom port\n"
        "  python app.py --data-dir D:\\MyImages   # Custom storage\n",
    )
    parser.add_argument(
        "--port", type=int, default=None, help=f"Server port (default {Config.PORT})"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Image storage directory (default: save to settings.json)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        default=is_frozen,
        help="Run with system tray icon (default: auto for packaged exe)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        default=False,
        help="Force console mode even when packaged",
    )
    return parser.parse_args()


def print_banner(port: int, local_ip: str):
    print()
    lines = [
        f"  >> {Config.SITE_TITLE}",
        f"  {'─' * 37}",
        f"  Local:        http://localhost:{port}",
        f"  LAN:          http://{local_ip}:{port}",
        f"  {'─' * 37}",
        f"  Storage:      {Config.UPLOAD_DIR}",
        f"  Thumbnails:   {Config.THUMBNAIL_DIR}",
        f"  Default group: {Config.DEFAULT_GROUP}",
        f"  Max upload:   {Config.MAX_CONTENT_LENGTH // (1024 * 1024)} MB",
        f"  {'─' * 37}",
        "  Press Ctrl+C to stop",
        "",
    ]
    for line in lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"))


def _apply_cli_args(args):
    """Apply CLI argument overrides to Config."""
    if args.port:
        Config.PORT = args.port
    if args.data_dir:
        Config.DATA_DIR = Path(args.data_dir)
        Config.UPLOAD_DIR = Config.DATA_DIR / "uploads"
        Config.THUMBNAIL_DIR = Config.DATA_DIR / "thumbnails"
        Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        Config.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        (Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
        (Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)


def _serve_console():
    """Run Flask in console mode (clean Ctrl+C handling)."""
    app.run(host=Config.HOST, port=Config.PORT, debug=False, use_reloader=False)


def _serve_tray():
    """Run Flask using make_server (needed for tray restart support)."""
    from werkzeug.serving import make_server

    global _http_server
    _http_server = make_server(Config.HOST, Config.PORT, app)
    _http_server.serve_forever()


def main_console():
    """Launch in console mode. Ctrl+C to stop. Restart manually after port change."""
    local_ip = get_local_ip()
    print_banner(local_ip=local_ip, port=Config.PORT)
    try:
        _serve_console()
    except KeyboardInterrupt:
        print("\nShutting down…")


def main_tray():
    """Launch with system-tray icon. Auto-restarts when tray says Restart."""
    local_ip = get_local_ip()
    print_banner(local_ip=local_ip, port=Config.PORT)

    server_stopped = threading.Event()

    def run_with_restart():
        while not server_stopped.is_set():
            _serve_tray()
            # When Flask stops (shutdown API called), check if we should restart
            if not server_stopped.is_set():
                # Small delay then re-enter _serve_tray for a clean restart
                time.sleep(0.3)

    server_thread = threading.Thread(target=run_with_restart, daemon=True)
    server_thread.start()

    # Run tray in main thread (blocking)
    try:
        import tray

        tray.run_tray(lambda: Config.PORT, server_stopped=server_stopped)
    except ImportError as e:
        print(f"Tray unavailable ({e}), falling back to console mode.")
        server_stopped.set()
    # Tray exited — clean up the server thread
    server_stopped.set()
    server_thread.join(timeout=2)


def main():
    args = parse_args()
    use_tray = args.tray and not args.no_tray

    _apply_cli_args(args)

    # Clean up leftover staged files from last run
    staging.cleanup_all_staging()

    if use_tray:
        main_tray()
    else:
        main_console()


if __name__ == "__main__":
    main()
