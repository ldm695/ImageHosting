"""
Utility functions for ImageHosting.

Pure functions that depend only on Config, standard library, and Flask's url_for.
"""
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from flask import url_for

from config import Config

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ── Shared constants ──────────────────────────────

# ext -> Pillow save format. Shared by thumbnail generation and staging
# preview so the mapping lives in one place.
THUMBNAIL_FORMAT_MAP = {
    '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG',
    '.gif': 'GIF', '.webp': 'WEBP', '.bmp': 'BMP',
}


# ── Atomic file writes ────────────────────────────

def atomic_write_text(path: Path, text: str, encoding: str = 'utf-8'):
    """Write text to `path` atomically.

    Writes to a temp file in the same directory then os.replace()s it into
    place, so a crash mid-write can never leave a half-written (corrupt) file.
    """
    path = Path(path)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(str(tmp), str(path))
    except Exception:
        # Best-effort cleanup of the temp file on failure.
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ── Tags ──────────────────────────────────────────

TAG_MAX_LEN = 64
_TAG_PATTERN = re.compile(r'^[\w\s\-]+$')

# Serializes the load->modify->write of any group's .tags.json. The dev
# server runs multithreaded (console mode), so concurrent requests tagging
# files in the same group would otherwise lose updates.
_tags_lock = threading.Lock()


def validate_tag(tag: str) -> tuple[bool, str]:
    """Validate a tag string. Returns (ok, error_message).

    Rules: non-empty after strip, <= 64 chars, only letters, numbers,
    spaces, hyphens, and underscores.
    """
    tag = (tag or '').strip()
    if not tag:
        return False, 'Tag cannot be empty'
    if len(tag) > TAG_MAX_LEN:
        return False, f'Tag must be {TAG_MAX_LEN} characters or fewer'
    if not _TAG_PATTERN.match(tag):
        return False, 'Tag can only contain letters, numbers, spaces, hyphens, and underscores'
    return True, ''


def load_tags(group: str = Config.DEFAULT_GROUP) -> dict[str, str]:
    """Load tag mapping from group's .tags.json (filename -> tag)."""
    tags_file = Config.UPLOAD_DIR / group / '.tags.json'
    if tags_file.exists():
        try:
            return json.loads(tags_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_tag(group: str, filename: str, tag: str):
    """Set a tag for a specific file in a group."""
    tag = tag.strip()
    if not tag:
        return
    with _tags_lock:
        tags = load_tags(group)
        tags[filename] = tag
        _write_tags(group, tags)


def remove_tag(group: str, filename: str):
    """Remove a tag entry for a specific file."""
    with _tags_lock:
        tags = load_tags(group)
        tags.pop(filename, None)
        _write_tags(group, tags)


def rename_tag_entry(group: str, old_name: str, new_name: str):
    """Rename a tag key when a file is renamed."""
    with _tags_lock:
        tags = load_tags(group)
        if old_name in tags:
            tags[new_name] = tags.pop(old_name)
            _write_tags(group, tags)


def move_tag_entry(from_group: str, to_group: str, filename: str):
    """Move a tag entry between groups."""
    with _tags_lock:
        src_tags = load_tags(from_group)
        if filename in src_tags:
            dst_tags = load_tags(to_group)
            dst_tags[filename] = src_tags.pop(filename)
            _write_tags(from_group, src_tags)
            _write_tags(to_group, dst_tags)


def delete_tag_entry(group: str, filename: str):
    """Remove a tag entry (when file is deleted). Alias for remove_tag."""
    remove_tag(group, filename)


def rename_tag_global(group: str, old_tag: str, new_tag: str) -> int:
    """Rename a tag across all images in a group. Returns count of updated files."""
    with _tags_lock:
        tags = load_tags(group)
        count = 0
        for fname, t in list(tags.items()):
            if t == old_tag:
                tags[fname] = new_tag
                count += 1
        if count:
            _write_tags(group, tags)
    return count


def delete_tag_global(group: str, tag: str) -> int:
    """Remove a tag from all images in a group. Returns count of updated files."""
    with _tags_lock:
        tags = load_tags(group)
        count = 0
        for fname, t in list(tags.items()):
            if t == tag:
                del tags[fname]
                count += 1
        if count:
            _write_tags(group, tags)
    return count


def _write_tags(group: str, tags: dict[str, str]):
    """Persist tags to disk. Caller must hold _tags_lock."""
    tags_file = Config.UPLOAD_DIR / group / '.tags.json'
    if tags:
        atomic_write_text(
            tags_file,
            json.dumps(tags, indent=2, ensure_ascii=False),
        )
    elif tags_file.exists():
        tags_file.unlink()


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in Config.ALLOWED_EXTENSIONS


def get_local_ip() -> str:
    """Get local LAN IP address"""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.1)
            s.connect(('10.255.255.255', 1))
            ip = s.getsockname()[0]
        return ip
    except Exception:
        return '127.0.0.1'


def format_size(size_bytes: int) -> str:
    """Format file size for human reading"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def is_valid_group_name(name: str) -> bool:
    """Validate group name"""
    if not name or len(name) > 64:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', name))


def generate_thumbnail(src_path: Path, dst_path: Path) -> bool:
    """Generate thumbnail, return True on success"""
    if not HAS_PIL:
        return False
    ext = src_path.suffix.lower()
    if ext not in Config.PILLOW_FORMATS:
        return False
    try:
        with Image.open(src_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGBA')

            img.thumbnail(Config.THUMBNAIL_SIZE, Image.LANCZOS)

            out_ext = dst_path.suffix.lower()
            fmt = THUMBNAIL_FORMAT_MAP.get(out_ext, 'JPEG')

            if fmt == 'JPEG' and img.mode == 'RGBA':
                img = img.convert('RGB')

            img.save(dst_path, fmt, quality=Config.THUMBNAIL_QUALITY)
            return True
    except Exception:
        return False


def load_dims(group: str = Config.DEFAULT_GROUP) -> dict[str, dict]:
    """Load the cached image-dimension map for a group.

    Shape: {filename: {'w': int, 'h': int, 'size': int}}. `size` is the
    file's byte size when measured — a mismatch means the file changed and
    the cache entry must be recomputed.
    """
    dims_file = Config.UPLOAD_DIR / group / '.dims.json'
    if dims_file.exists():
        try:
            data = json.loads(dims_file.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def write_dims(group: str, dims: dict[str, dict]):
    """Persist the dimension cache to disk (atomic)."""
    dims_file = Config.UPLOAD_DIR / group / '.dims.json'
    if dims:
        atomic_write_text(
            dims_file,
            json.dumps(dims, ensure_ascii=False),
        )
    elif dims_file.exists():
        dims_file.unlink()


def get_image_info(filename: str, group: str = Config.DEFAULT_GROUP,
                   tags: dict[str, str] | None = None,
                   dims_cache: dict[str, dict] | None = None) -> dict | None:
    """Get single image metadata (includes tag if set).

    Pass a preloaded `tags` mapping to avoid re-reading .tags.json per call
    (used by scan_images to avoid an N+1 read).

    Pass a `dims_cache` dict to reuse previously measured width/height instead
    of opening every image with Pillow. On a cache miss (or a changed file)
    the dimensions are measured and written back into the passed dict, so the
    caller can persist the updated cache once after a full scan.
    """
    filepath = Config.UPLOAD_DIR / group / filename
    if not filepath.exists() or not filepath.is_file():
        return None

    ext = filepath.suffix.lower()
    stat = filepath.stat()

    width = height = None
    if ext in Config.PILLOW_FORMATS and HAS_PIL:
        cached = dims_cache.get(filename) if dims_cache is not None else None
        if cached and cached.get('size') == stat.st_size:
            width, height = cached.get('w'), cached.get('h')
        else:
            try:
                with Image.open(filepath) as img:
                    width, height = img.size
                if dims_cache is not None and width and height:
                    dims_cache[filename] = {
                        'w': width, 'h': height, 'size': stat.st_size,
                    }
            except Exception:
                pass

    created_dt = datetime.fromtimestamp(stat.st_ctime)
    if tags is None:
        tags = load_tags(group)

    info = {
        'filename': filename,
        'group': group,
        'url': url_for('serve_upload', group=group, filename=filename),
        'thumbnail_url': url_for('serve_thumbnail', group=group, filename=filename),
        'absolute_path': str(filepath.resolve()),
        'size': stat.st_size,
        'formatted_size': format_size(stat.st_size),
        'created': created_dt.isoformat(),
        'created_formatted': created_dt.strftime('%Y-%m-%d %H:%M'),
    }
    if width and height:
        info['width'] = width
        info['height'] = height
    if filename in tags:
        info['tag'] = tags[filename]
    return info


def scan_images(group: str = Config.DEFAULT_GROUP, tag_filter: str | None = None) -> dict:
    """Scan group directory, return images + tag list.

    Returns: {'images': [...], 'tags': [...]}
    """
    group_dir = Config.UPLOAD_DIR / group
    if not group_dir.exists():
        return {'images': [], 'tags': []}

    tags = load_tags(group)
    tag_set = set(t for t in tags.values() if t)

    dims_cache = load_dims(group)
    dims_before = json.dumps(dims_cache, sort_keys=True)
    present = set()

    images = []
    for f in sorted(group_dir.iterdir(),
                     key=lambda p: p.stat().st_ctime, reverse=True):
        if f.is_file() and allowed_file(f.name):
            present.add(f.name)
            if tag_filter and tags.get(f.name) != tag_filter:
                continue
            info = get_image_info(f.name, group, tags=tags, dims_cache=dims_cache)
            if info:
                images.append(info)

    # Drop cache entries for files that no longer exist, then persist if the
    # cache changed (new measurements or pruned stale entries).
    for stale in [k for k in dims_cache if k not in present]:
        del dims_cache[stale]
    if json.dumps(dims_cache, sort_keys=True) != dims_before:
        try:
            write_dims(group, dims_cache)
        except Exception:
            pass

    return {
        'images': images,
        'tags': sorted(tag_set),
    }


def scan_groups() -> list[dict]:
    """Scan all groups (subdirectories), sorted default first then alpha"""
    groups = []
    for d in sorted(Config.UPLOAD_DIR.iterdir()):
        if d.is_dir():
            count = 0
            try:
                count = len([f for f in d.iterdir()
                            if f.is_file() and allowed_file(f.name)])
            except Exception:
                pass
            groups.append({
                'name': d.name,
                'count': count,
            })
    # Default group first
    groups.sort(key=lambda g: (0 if g['name'] == Config.DEFAULT_GROUP else 1, g['name']))
    return groups


def ensure_group_dirs(group: str):
    """Ensure group directories exist"""
    (Config.UPLOAD_DIR / group).mkdir(parents=True, exist_ok=True)
    (Config.THUMBNAIL_DIR / group).mkdir(parents=True, exist_ok=True)


def is_port_available(port: int) -> bool:
    """Check if a TCP port is available for binding."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return True
        except OSError:
            return False
