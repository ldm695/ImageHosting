"""Image + tag + batch routes (upload / delete / rename / tag / move / batch)."""
import os
import json
import shutil
from pathlib import Path

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from config import Config
from utils import (
    allowed_file, validate_tag, get_image_info, scan_images,
    save_tag, remove_tag, delete_tag_entry, rename_tag_entry, move_tag_entry,
    rename_tag_global, delete_tag_global, ensure_group_dirs, generate_thumbnail,
)
from helpers import with_query_group, group_error, safe_or_error

bp = Blueprint('images', __name__)


# ── Listing ──────────────────────────────────────

@bp.route('/api/images')
@with_query_group
def api_images(group):
    """Get images for a specific group, optional tag filter"""
    tag_filter = request.args.get('tag', '').strip() or None
    return jsonify(scan_images(group, tag_filter=tag_filter))


# ── Upload ───────────────────────────────────────

@bp.route('/api/upload', methods=['POST'])
@with_query_group
def api_upload(group):
    """Upload images (single or multiple, to a specific group)"""
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

    # Optional tags: a single `tag` applies to all files; a `tags` JSON
    # array assigns per-file tags by index (takes precedence over `tag`).
    default_tag = (request.form.get('tag', '') or '').strip()
    per_file_tags = []
    raw_tags = request.form.get('tags', '')
    if raw_tags:
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                per_file_tags = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    if default_tag:
        ok, err = validate_tag(default_tag)
        if not ok:
            return jsonify({'error': err}), 400

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

        # Validate filename (reject unsafe characters, no auto-sanitize)
        safe = secure_filename(use_name)
        if not safe or safe != use_name:
            errors.append({
                'filename': file.filename,
                'error': 'Filename contains invalid or unsafe characters. Use only letters, numbers, dots, underscores, and hyphens.'
            })
            continue

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

        # Apply tag (per-file overrides the default; invalid tags skipped)
        file_tag = default_tag
        if i < len(per_file_tags) and per_file_tags[i]:
            candidate = str(per_file_tags[i]).strip()
            if candidate:
                ok, _ = validate_tag(candidate)
                file_tag = candidate if ok else file_tag
        if file_tag:
            save_tag(group, safe, file_tag)

        info = get_image_info(safe, group)
        if info:
            uploaded.append(info)

    return jsonify({'uploaded': uploaded, 'errors': errors})


# ── Single-image operations ──────────────────────

@bp.route('/api/image/<filename>', methods=['DELETE'])
@with_query_group
def api_delete_image(filename, group):
    """Delete an image (original + thumbnail)"""
    safe, err = safe_or_error(filename)
    if err:
        return err

    filepath = Config.UPLOAD_DIR / group / safe
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    try:
        filepath.unlink()
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500

    # Remove tag entry
    delete_tag_entry(group, safe)

    thumbpath = Config.THUMBNAIL_DIR / group / safe
    if thumbpath.exists():
        try:
            thumbpath.unlink()
        except Exception:
            pass

    return jsonify({'success': True, 'filename': safe})


@bp.route('/api/image/<filename>/rename', methods=['PUT'])
@with_query_group
def api_rename_image(filename, group):
    """Rename an image within its group"""
    data = request.get_json(silent=True) or {}
    new_name = (data.get('new_name', '') or '').strip()

    if not new_name:
        return jsonify({'error': 'New filename is required'}), 400

    safe_old, err = safe_or_error(filename, 'original filename')
    if err:
        return err
    safe_new, err = safe_or_error(new_name, 'new filename')
    if err:
        return err

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

    # Sync tag entry
    rename_tag_entry(group, safe_old, safe_new)

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


@bp.route('/api/image/<filename>/tag', methods=['PUT'])
@with_query_group
def api_set_tag(filename, group):
    """Set or update the tag for an image."""
    data = request.get_json(silent=True) or {}
    tag = (data.get('tag', '') or '').strip()

    safe, err = safe_or_error(filename)
    if err:
        return err

    filepath = Config.UPLOAD_DIR / group / safe
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    ok, verr = validate_tag(tag)
    if not ok:
        return jsonify({'error': verr}), 400

    save_tag(group, safe, tag)
    info = get_image_info(safe, group)
    return jsonify({'success': True, 'tag': tag, 'info': info})


@bp.route('/api/image/<filename>/tag', methods=['DELETE'])
@with_query_group
def api_remove_tag(filename, group):
    """Remove the tag from an image."""
    safe, err = safe_or_error(filename)
    if err:
        return err

    filepath = Config.UPLOAD_DIR / group / safe
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    remove_tag(group, safe)
    info = get_image_info(safe, group)
    return jsonify({'success': True, 'info': info})


@bp.route('/api/image/<filename>/move', methods=['PUT'])
def api_move_image(filename):
    """Move an image to another group"""
    from_group = request.args.get('group', Config.DEFAULT_GROUP)
    err = group_error(from_group)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    to_group = (data.get('to_group', '') or '').strip()

    if not to_group:
        return jsonify({'error': 'Target group is required'}), 400
    if group_error(to_group):
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

    # Sync tag entry
    move_tag_entry(from_group, to_group, safe_file)

    info = get_image_info(safe_file, to_group)
    return jsonify({'success': True, 'filename': safe_file, 'group': to_group, 'info': info})


# ── Global tag operations ────────────────────────

@bp.route('/api/tags/<tag>', methods=['PUT'])
@with_query_group
def api_rename_tag_global(tag, group):
    """Rename a tag globally across all images in a group."""
    data = request.get_json(silent=True) or {}
    new_tag = (data.get('new_tag', '') or '').strip()

    ok, err = validate_tag(new_tag)
    if not ok:
        return jsonify({'error': err}), 400
    if new_tag == tag:
        return jsonify({'error': 'New tag is the same as the old one'}), 400

    count = rename_tag_global(group, tag, new_tag)
    return jsonify({'success': True, 'old_tag': tag, 'new_tag': new_tag, 'updated': count})


@bp.route('/api/tags/<tag>', methods=['DELETE'])
@with_query_group
def api_delete_tag_global(tag, group):
    """Remove a tag from all images in a group."""
    count = delete_tag_global(group, tag)
    return jsonify({'success': True, 'tag': tag, 'removed': count})


# ── Batch operations ─────────────────────────────

@bp.route('/api/images/batch-delete', methods=['POST'])
def api_batch_delete():
    """Delete multiple images at once"""
    data = request.get_json(silent=True) or {}
    group = data.get('group', Config.DEFAULT_GROUP)
    files = data.get('files', [])

    if group_error(group):
        return jsonify({'error': 'Invalid group name'}), 400
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
            delete_tag_entry(group, safe)
            results['deleted'].append(filename)
        except Exception as e:
            results['errors'].append({'filename': filename, 'error': str(e)})

    return jsonify({'success': True, **results})


@bp.route('/api/images/batch-move', methods=['POST'])
def api_batch_move():
    """Move multiple images to another group"""
    data = request.get_json(silent=True) or {}
    group = data.get('group', Config.DEFAULT_GROUP)
    to_group = data.get('to_group', '').strip()
    files = data.get('files', [])

    if group_error(group):
        return jsonify({'error': 'Invalid group name'}), 400
    if not files or not isinstance(files, list):
        return jsonify({'error': 'File list is required'}), 400
    if not to_group:
        return jsonify({'error': 'Target group is required'}), 400
    if group_error(to_group):
        return jsonify({'error': 'Invalid target group name'}), 400
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
            move_tag_entry(group, to_group, safe)
            results['moved'].append(filename)
        except Exception as e:
            results['errors'].append({'filename': filename, 'error': str(e)})

    return jsonify({'success': True, **results})


@bp.route('/api/images/batch-tag', methods=['POST'])
def api_batch_tag():
    """Set the same tag for multiple images at once."""
    data = request.get_json(silent=True) or {}
    group = data.get('group', Config.DEFAULT_GROUP)
    tag = (data.get('tag', '') or '').strip()
    files = data.get('files', [])

    if group_error(group):
        return jsonify({'error': 'Invalid group name'}), 400
    if not files or not isinstance(files, list):
        return jsonify({'error': 'File list is required'}), 400
    ok, err = validate_tag(tag)
    if not ok:
        return jsonify({'error': err}), 400

    results = {'tagged': [], 'errors': []}

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
            save_tag(group, safe, tag)
            results['tagged'].append(filename)
        except Exception as e:
            results['errors'].append({'filename': filename, 'error': str(e)})

    return jsonify({'success': True, 'tag': tag, **results})
