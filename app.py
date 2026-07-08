"""
ImageHosting — Local image hosting service
===========================================
Single-user LAN image hosting with Groups / Upload / Browse / Delete / Copy links / Thumbnails
"""
import os
import sys
import re
import json
import shutil
import argparse
import threading
import mimetypes
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, url_for
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config

# ── Settings persistence ─────────────────────────

SETTINGS_FILE = Config.DATA_DIR / 'settings.json'


def load_settings() -> dict:
    """Load settings from settings.json"""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(data: dict):
    """Save settings to settings.json (merges with existing)"""
    current = load_settings()
    current.update(data)
    SETTINGS_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


# ── App Init ─────────────────────────────────────

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

# Apply persisted settings
_persisted = load_settings()
if 'data_dir' in _persisted and not any(a.startswith('--data-dir') for a in sys.argv[1:]):
    Config.DATA_DIR = Path(_persisted['data_dir'])
    Config.UPLOAD_DIR = Config.DATA_DIR / 'uploads'
    Config.THUMBNAIL_DIR = Config.DATA_DIR / 'thumbnails'
if 'staging_timeout' in _persisted:
    Config.STAGING_TIMEOUT = int(_persisted['staging_timeout'])
if 'port' in _persisted and not any(a.startswith('--port') for a in sys.argv[1:]):
    Config.PORT = int(_persisted['port'])

# Ensure root dirs exist
Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Config.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
# Ensure default group dirs exist
(Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
(Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
# Ensure staging dir exists and clean leftover files from last run
Config.STAGING_DIR.mkdir(parents=True, exist_ok=True)

# Register MIME types
mimetypes.add_type('image/webp', '.webp')
mimetypes.add_type('image/avif', '.avif')

# ── Utilities ────────────────────────────────────

from utils import *  # noqa: F403, E402

# ── Staging (upload confirmation) ─────────────────

# Register this module as 'app' so staging.py's 'from app import app' works
import sys
sys.modules['app'] = sys.modules[__name__]

import staging  # noqa: F811, E402
# cleanup_all_staging() is called in main() after all imports

_http_server = None  # Set by make_server in _serve_forever()

# ── Page Routes ─────────────────────────────────

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html',
        title=Config.SITE_TITLE,
        port=Config.PORT,
        local_ip=get_local_ip(),
        max_size_mb=Config.MAX_CONTENT_LENGTH // (1024 * 1024),
        default_group=Config.DEFAULT_GROUP,
        data_dir=str(Config.DATA_DIR),
    )


# ── Settings API ─────────────────────────────────

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """Get current settings"""
    return jsonify({
        'data_dir': str(Config.DATA_DIR),
        'port': Config.PORT,
        'staging_timeout': Config.STAGING_TIMEOUT,
    })


@app.route('/api/settings/browse', methods=['POST'])
def api_browse_folder():
    """Open native folder-picker dialog via tkinter, return selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='Select Image Storage Directory')
        root.destroy()
        if folder:
            return jsonify({'path': folder})
        return jsonify({'path': None, 'error': 'No folder selected'}), 400
    except ImportError:
        return jsonify({'error': 'tkinter not available on this system'}), 501
    except Exception as e:
        return jsonify({'error': f'Failed to open folder picker: {str(e)}'}), 500



@app.route('/api/settings/data-dir', methods=['PUT'])
def api_update_data_dir():
    """Update storage directory with file migration."""
    data = request.get_json(silent=True) or {}
    new_dir = (data.get('data_dir', '') or '').strip()

    if not new_dir:
        return jsonify({'error': 'Directory path is required'}), 400

    new_root = Path(new_dir).resolve()
    old_root = Config.DATA_DIR.resolve()

    if new_root == old_root:
        return jsonify({'error': 'New directory is the same as the current one'}), 400
    if not new_root.parent.exists():
        return jsonify({'error': f'Parent directory "{new_root.parent}" does not exist'}), 400

    new_upload = new_root / 'uploads'
    new_thumb = new_root / 'thumbnails'

    try:
        new_upload.mkdir(parents=True, exist_ok=True)
        new_thumb.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = new_upload / '.write_test'
        test_file.write_text('test')
        test_file.unlink()
    except Exception as e:
        return jsonify({'error': f'Cannot write to directory: {str(e)}'}), 400

    migration_log = {'moved_uploads': 0, 'moved_thumbnails': 0, 'groups': []}

    try:
        # Migrate each group from old to new
        if Config.UPLOAD_DIR.exists():
            for group_dir in Config.UPLOAD_DIR.iterdir():
                if not group_dir.is_dir():
                    continue
                gname = group_dir.name

                # Migrate original images
                files = [f for f in group_dir.iterdir()
                        if f.is_file() and allowed_file(f.name)]
                if files:
                    dst_dir = new_upload / gname
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    for f in files:
                        shutil.move(str(f), str(dst_dir / f.name))
                        migration_log['moved_uploads'] += 1

                # Migrate thumbnails for this group
                old_td = Config.THUMBNAIL_DIR / gname
                if old_td.exists():
                    tfiles = [f for f in old_td.iterdir() if f.is_file()]
                    if tfiles:
                        new_td = new_thumb / gname
                        new_td.mkdir(parents=True, exist_ok=True)
                        for f in tfiles:
                            shutil.move(str(f), str(new_td / f.name))
                            migration_log['moved_thumbnails'] += 1

                migration_log['groups'].append(gname)

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
        migration_log['error'] = str(e)

    # Switch at runtime
    Config.DATA_DIR = new_root
    Config.UPLOAD_DIR = new_upload
    Config.THUMBNAIL_DIR = new_thumb

    # Ensure default group exists in new location
    (Config.UPLOAD_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)
    (Config.THUMBNAIL_DIR / Config.DEFAULT_GROUP).mkdir(parents=True, exist_ok=True)

    save_settings({'data_dir': str(new_root)})

    msg = 'Storage directory updated instantly.'
    if migration_log['moved_uploads'] > 0:
        msg += f' Migrated {migration_log["moved_uploads"]} image(s).'
    if migration_log.get('error'):
        msg += f' Warning: partial migration - {migration_log["error"]}'

    return jsonify({
        'success': True,
        'message': msg,
        'data_dir': str(new_root),
        'migration': migration_log,
    })


@app.route('/api/settings/staging-timeout', methods=['PUT'])
def api_update_staging_timeout():
    """Update staging timeout only."""
    data = request.get_json(silent=True) or {}
    new_timeout = data.get('staging_timeout')

    if new_timeout is None:
        return jsonify({'error': 'staging_timeout is required'}), 400

    try:
        timeout = int(new_timeout)
        if timeout < 10 or timeout > 3600:
            return jsonify({'error': 'Staging timeout must be between 10 and 3600 seconds'}), 400
        Config.STAGING_TIMEOUT = timeout
        save_settings({'staging_timeout': timeout})
        return jsonify({'success': True, 'staging_timeout': timeout})
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid timeout value'}), 400


@app.route('/api/settings/port', methods=['PUT'])
def api_update_port():
    """Update server port with availability check and auto-restart."""
    data = request.get_json(silent=True) or {}
    new_port = data.get('port')

    if new_port is None:
        return jsonify({'error': 'port is required'}), 400

    try:
        port = int(new_port)
        if port < 1024 or port > 65535:
            return jsonify({'error': 'Port must be between 1024 and 65535'}), 400
        if port == Config.PORT:
            return jsonify({'error': 'Port is the same as the current one'}), 400

        # Save to settings.json only — takes effect on next restart
        save_settings({'port': port})

        return jsonify({'success': True, 'saved_port': port, '_applied_on_restart': True})
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid port value'}), 400

# ── Group API ────────────────────────────────────

@app.route('/api/groups', methods=['GET'])
def api_list_groups():
    """List all groups"""
    return jsonify(scan_groups())


@app.route('/api/groups', methods=['POST'])
def api_create_group():
    """Create a new group"""
    data = request.get_json(silent=True) or {}
    name = (data.get('name', '') or '').strip()

    if not name:
        return jsonify({'error': 'Group name is required'}), 400
    if not is_valid_group_name(name):
        return jsonify({'error': 'Group name can only contain letters, numbers, underscores, and hyphens'}), 400

    group_dir = Config.UPLOAD_DIR / name
    if group_dir.exists():
        return jsonify({'error': f'Group "{name}" already exists'}), 409

    ensure_group_dirs(name)
    return jsonify({'success': True, 'name': name}), 201


@app.route('/api/groups/<name>', methods=['DELETE'])
def api_delete_group(name):
    """Delete a group and all its images"""
    if name == Config.DEFAULT_GROUP:
        return jsonify({'error': 'Cannot delete the default group'}), 400
    if not is_valid_group_name(name):
        return jsonify({'error': 'Invalid group name'}), 400

    group_dir = Config.UPLOAD_DIR / name
    thumb_dir = Config.THUMBNAIL_DIR / name

    if not group_dir.exists():
        return jsonify({'error': 'Group not found'}), 404

    try:
        shutil.rmtree(str(group_dir))
        if thumb_dir.exists():
            shutil.rmtree(str(thumb_dir))
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

    return jsonify({'success': True})


@app.route('/api/groups/<name>', methods=['PUT'])
def api_rename_group(name):
    """Rename a group"""
    if name == Config.DEFAULT_GROUP:
        return jsonify({'error': 'Cannot rename the default group'}), 400

    data = request.get_json(silent=True) or {}
    new_name = (data.get('new_name', '') or '').strip()

    if not new_name:
        return jsonify({'error': 'New name is required'}), 400
    if not is_valid_group_name(new_name):
        return jsonify({'error': 'Name can only contain letters, numbers, underscores, and hyphens'}), 400

    old_dir = Config.UPLOAD_DIR / name
    new_dir = Config.UPLOAD_DIR / new_name
    if not old_dir.exists():
        return jsonify({'error': 'Group not found'}), 404
    if new_dir.exists():
        return jsonify({'error': f'Group "{new_name}" already exists'}), 409

    old_thumb = Config.THUMBNAIL_DIR / name
    new_thumb = Config.THUMBNAIL_DIR / new_name

    try:
        old_dir.rename(new_dir)
        if old_thumb.exists():
            old_thumb.rename(new_thumb)
    except Exception as e:
        return jsonify({'error': f'Rename failed: {str(e)}'}), 500

    return jsonify({'success': True, 'name': new_name}), 200


# ── Image API ────────────────────────────────────

@app.route('/api/images')
def api_images():
    """Get images for a specific group"""
    group = request.args.get('group', Config.DEFAULT_GROUP)
    return jsonify(scan_images(group))


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload images (single or multiple, to a specific group)"""
    group = request.args.get('group', Config.DEFAULT_GROUP)
    ensure_group_dirs(group)

    if 'files' not in request.files:
        return jsonify({'error': 'No file data in request'}), 400

    files = request.files.getlist('files')
    files = [f for f in files if f and f.filename and f.filename.strip()]

    if not files:
        return jsonify({'error': 'Please select files to upload'}), 400

    # Optional custom filenames (JSON array, one per file, by index)
    custom_names = []
    raw = request.form.get('filenames', '')
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                custom_names = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    uploaded = []
    errors = []

    for i, file in enumerate(files):
        if not allowed_file(file.filename):
            errors.append({
                'filename': file.filename,
                'error': f'Unsupported format. Allowed: {", ".join(sorted(Config.ALLOWED_EXTENSIONS))}'
            })
            continue

        # Determine effective filename (custom name if provided)
        # Make sure extension is preserved from the original file
        _, orig_ext = os.path.splitext(file.filename)
        use_name = file.filename
        if i < len(custom_names) and custom_names[i]:
            cn = custom_names[i].strip()
            if cn:
                # Ensure it has the same extension
                cn_base, cn_ext = os.path.splitext(cn)
                if not cn_ext:
                    cn += orig_ext.lower()
                use_name = cn

        # Get safe filename but REJECT if already exists (no auto-rename)
        safe = secure_filename(use_name)
        if not safe or Path(safe).stem == '':
            name, ext = os.path.splitext(use_name)
            ext = ext.lower()
            safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
            safe = re.sub(r'\s+', '_', safe).strip('._')
            if not safe:
                safe = 'image'
            safe += ext

        filepath = Config.UPLOAD_DIR / group / safe
        if filepath.exists():
            errors.append({
                'filename': file.filename,
                'error': f'File "{safe}" already exists in this group'
            })
            continue

        try:
            file.save(str(filepath))
        except Exception as e:
            errors.append({'filename': file.filename, 'error': f'Save failed: {str(e)}'})
            continue

        # Generate thumbnail
        ext = filepath.suffix.lower()
        if ext in Config.PILLOW_FORMATS:
            thumbpath = Config.THUMBNAIL_DIR / group / safe
            generate_thumbnail(filepath, thumbpath)

        info = get_image_info(safe, group)
        if info:
            uploaded.append(info)

    return jsonify({'uploaded': uploaded, 'errors': errors})


@app.route('/api/image/<filename>', methods=['DELETE'])
def api_delete_image(filename):
    """Delete an image (original + thumbnail)"""
    group = request.args.get('group', Config.DEFAULT_GROUP)
    safe = secure_filename(filename)
    if not safe:
        return jsonify({'error': 'Invalid filename'}), 400

    filepath = Config.UPLOAD_DIR / group / safe
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    try:
        filepath.unlink()
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

    thumbpath = Config.THUMBNAIL_DIR / group / safe
    if thumbpath.exists():
        try:
            thumbpath.unlink()
        except Exception:
            pass

    return jsonify({'success': True, 'filename': safe})


@app.route('/api/image/<filename>/rename', methods=['PUT'])
def api_rename_image(filename):
    """Rename an image within its group"""
    group = request.args.get('group', Config.DEFAULT_GROUP)
    data = request.get_json(silent=True) or {}
    new_name = (data.get('new_name', '') or '').strip()

    if not new_name:
        return jsonify({'error': 'New filename is required'}), 400

    safe_old = secure_filename(filename)
    safe_new = secure_filename(new_name)

    if not safe_old:
        return jsonify({'error': 'Invalid original filename'}), 400
    if not safe_new:
        return jsonify({'error': 'Invalid new filename'}), 400

    # Extension must match
    old_ext = Path(safe_old).suffix.lower()
    new_ext = Path(safe_new).suffix.lower()
    if old_ext != new_ext:
        return jsonify({'error': f'Extension must remain the same ({old_ext})'}), 400

    old_path = Config.UPLOAD_DIR / group / safe_old
    new_path = Config.UPLOAD_DIR / group / safe_new

    if not old_path.exists():
        return jsonify({'error': 'File not found'}), 404
    if new_path.exists():
        return jsonify({'error': 'A file with that name already exists'}), 409

    try:
        old_path.rename(new_path)
    except Exception as e:
        return jsonify({'error': f'Rename failed: {str(e)}'}), 500

    # Rename thumbnail if it exists
    old_thumb = Config.THUMBNAIL_DIR / group / safe_old
    new_thumb = Config.THUMBNAIL_DIR / group / safe_new
    if old_thumb.exists():
        try:
            old_thumb.rename(new_thumb)
        except Exception:
            pass

    info = get_image_info(safe_new, group)
    return jsonify({'success': True, 'filename': safe_new, 'info': info})


@app.route('/api/image/<filename>/move', methods=['PUT'])
def api_move_image(filename):
    """Move an image to another group"""
    from_group = request.args.get('group', Config.DEFAULT_GROUP)
    data = request.get_json(silent=True) or {}
    to_group = (data.get('to_group', '') or '').strip()

    if not to_group:
        return jsonify({'error': 'Target group is required'}), 400
    if not is_valid_group_name(to_group):
        return jsonify({'error': 'Invalid target group name'}), 400
    if to_group == from_group:
        return jsonify({'error': 'Target group is the same as the current group'}), 400

    safe_file = secure_filename(filename)
    if not safe_file or not allowed_file(safe_file):
        return jsonify({'error': 'Invalid filename'}), 400

    src_path = Config.UPLOAD_DIR / from_group / safe_file
    dst_path = Config.UPLOAD_DIR / to_group / safe_file

    if not src_path.exists():
        return jsonify({'error': 'File not found'}), 404
    if dst_path.exists():
        return jsonify({'error': f'A file named "{safe_file}" already exists in "{to_group}"'}), 409

    # Ensure target group dirs exist
    ensure_group_dirs(to_group)

    try:
        shutil.move(str(src_path), str(dst_path))
    except Exception as e:
        return jsonify({'error': f'Move failed: {str(e)}'}), 500

    # Move thumbnail
    src_thumb = Config.THUMBNAIL_DIR / from_group / safe_file
    dst_thumb = Config.THUMBNAIL_DIR / to_group / safe_file
    if src_thumb.exists():
        try:
            src_thumb.rename(dst_thumb)
        except Exception:
            pass

    info = get_image_info(safe_file, to_group)
    return jsonify({'success': True, 'filename': safe_file, 'group': to_group, 'info': info})


# ── Batch Operations ────────────────────────────

@app.route('/api/images/batch-delete', methods=['POST'])
def api_batch_delete():
    """Delete multiple images at once"""
    data = request.get_json(silent=True) or {}
    group = data.get('group', Config.DEFAULT_GROUP)
    files = data.get('files', [])

    if not files or not isinstance(files, list):
        return jsonify({'error': 'File list is required'}), 400

    results = {'deleted': [], 'errors': []}

    for filename in files:
        safe = secure_filename(filename)
        if not safe:
            results['errors'].append({'filename': filename, 'error': 'Invalid filename'})
            continue

        filepath = Config.UPLOAD_DIR / group / safe
        if not filepath.exists():
            results['errors'].append({'filename': filename, 'error': 'Not found'})
            continue

        try:
            filepath.unlink()
            thumbpath = Config.THUMBNAIL_DIR / group / safe
            if thumbpath.exists():
                thumbpath.unlink()
            results['deleted'].append(filename)
        except Exception as e:
            results['errors'].append({'filename': filename, 'error': str(e)})

    return jsonify({'success': True, **results})


@app.route('/api/images/batch-move', methods=['POST'])
def api_batch_move():
    """Move multiple images to another group"""
    data = request.get_json(silent=True) or {}
    group = data.get('group', Config.DEFAULT_GROUP)
    to_group = data.get('to_group', '').strip()
    files = data.get('files', [])

    if not files or not isinstance(files, list):
        return jsonify({'error': 'File list is required'}), 400
    if not to_group:
        return jsonify({'error': 'Target group is required'}), 400
    if to_group == group:
        return jsonify({'error': 'Target group is the same as the current group'}), 400

    ensure_group_dirs(to_group)
    results = {'moved': [], 'errors': []}

    for filename in files:
        safe = secure_filename(filename)
        if not safe or not allowed_file(safe):
            results['errors'].append({'filename': filename, 'error': 'Invalid filename'})
            continue

        src = Config.UPLOAD_DIR / group / safe
        dst = Config.UPLOAD_DIR / to_group / safe

        if not src.exists():
            results['errors'].append({'filename': filename, 'error': 'Not found'})
            continue
        if dst.exists():
            results['errors'].append({'filename': filename, 'error': 'Already exists in target'})
            continue

        try:
            shutil.move(str(src), str(dst))
            # Move thumbnail
            src_thumb = Config.THUMBNAIL_DIR / group / safe
            dst_thumb = Config.THUMBNAIL_DIR / to_group / safe
            if src_thumb.exists():
                src_thumb.rename(dst_thumb)
            results['moved'].append(filename)
        except Exception as e:
            results['errors'].append({'filename': filename, 'error': str(e)})

    return jsonify({'success': True, **results})


# ── Static File Routes ──────────────────────────

@app.route('/uploads/<group>/<filename>')
def serve_upload(group, filename):
    """Serve original image"""
    safe_group = secure_filename(group) or Config.DEFAULT_GROUP
    safe_file = secure_filename(filename)
    return send_from_directory(str(Config.UPLOAD_DIR / safe_group), safe_file)


@app.route('/thumbnails/<group>/<filename>')
def serve_thumbnail(group, filename):
    """Serve thumbnail (fallback to original if missing)"""
    safe_group = secure_filename(group) or Config.DEFAULT_GROUP
    safe_file = secure_filename(filename)
    thumbpath = Config.THUMBNAIL_DIR / safe_group / safe_file
    if thumbpath.exists():
        return send_from_directory(str(Config.THUMBNAIL_DIR / safe_group), safe_file)
    return send_from_directory(str(Config.UPLOAD_DIR / safe_group), safe_file)


# ── System API ──────────────────────────────────

@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """Shut down the server (used by tray restart / Exit)."""
    if _http_server is not None:
        srv = _http_server
        threading.Timer(0.5, lambda: srv.shutdown() if srv else None).start()
    return jsonify({'success': True})


@app.route('/api/status', methods=['GET'])
def api_status():
    """Simple health-check endpoint (used by tray icon)"""
    return jsonify({'status': 'running', 'port': Config.PORT})


# ── Error Handlers ───────────────────────────────

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({'error': f'File too large. Maximum: {Config.MAX_CONTENT_LENGTH // (1024 * 1024)} MB'}), 413


@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return render_template('index.html', title=Config.SITE_TITLE), 404


# ── Entry ────────────────────────────────────────

def parse_args():
    is_frozen = getattr(sys, 'frozen', False)
    parser = argparse.ArgumentParser(
        description='ImageHosting — Local image hosting service',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  python app.py                          # Console mode\n'
               '  python app.py --tray                   # Tray icon mode\n'
               '  python app.py --port 8080              # Custom port\n'
               '  python app.py --data-dir D:\\MyImages   # Custom storage\n'
    )
    parser.add_argument('--port', type=int, default=None,
                        help=f'Server port (default {Config.PORT})')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='Image storage directory (default: save to settings.json)')
    parser.add_argument('--tray', action='store_true', default=is_frozen,
                        help='Run with system tray icon (default: auto for packaged exe)')
    parser.add_argument('--no-tray', action='store_true', default=False,
                        help='Force console mode even when packaged')
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
        f"  Press Ctrl+C to stop",
        "",
    ]
    for line in lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode('ascii', errors='replace').decode('ascii'))


def _apply_cli_args(args):
    """Apply CLI argument overrides to Config."""
    if args.port:
        Config.PORT = args.port
    if args.data_dir:
        Config.DATA_DIR = Path(args.data_dir)
        Config.UPLOAD_DIR = Config.DATA_DIR / 'uploads'
        Config.THUMBNAIL_DIR = Config.DATA_DIR / 'thumbnails'
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

    import threading
    server_stopped = threading.Event()

    def run_with_restart():
        while not server_stopped.is_set():
            _serve_tray()
            # When Flask stops (shutdown API called), check if we should restart
            if not server_stopped.is_set():
                # Small delay then re-enter _serve_tray for a clean restart
                time.sleep(0.3)

    import time
    server_thread = threading.Thread(target=run_with_restart, daemon=True)
    server_thread.start()

    # Run tray in main thread (blocking)
    try:
        import tray
        tray.run_tray(lambda: Config.PORT, server_stopped=server_stopped)
    except ImportError as e:
        print(f"Tray unavailable ({e}), falling back to console mode.")
        server_stopped.set()
        # Fall back: just wait for the server thread
        server_thread.join()


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


if __name__ == '__main__':
    main()
