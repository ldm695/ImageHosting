"""
Utility functions for ImageHosting.

Pure functions that depend only on Config, standard library, and Flask's url_for.
"""
import os
import re
from datetime import datetime
from pathlib import Path

from flask import url_for
from werkzeug.utils import secure_filename

from config import Config

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


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


def make_safe_filename(filename: str, group: str = Config.DEFAULT_GROUP) -> str:
    """
    Generate a safe filename (with group-level duplicate detection)
    """
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    safe = secure_filename(filename)
    if not safe or Path(safe).stem == '':
        safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
        safe = re.sub(r'\s+', '_', safe).strip('._')
        if not safe:
            safe = 'image'
        safe += ext

    # Check duplicates within group
    stem, ext = os.path.splitext(safe)
    counter = 0
    while (Config.UPLOAD_DIR / group / safe).exists():
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe = f"{stem}_{ts}{ext}"
        counter += 1
        if counter > 100:
            break

    return safe


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
            fmt = {
                '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG',
                '.gif': 'GIF', '.webp': 'WEBP', '.bmp': 'BMP',
            }.get(out_ext, 'JPEG')

            if fmt == 'JPEG' and img.mode == 'RGBA':
                img = img.convert('RGB')

            img.save(dst_path, fmt, quality=Config.THUMBNAIL_QUALITY)
            return True
    except Exception:
        return False


def get_image_info(filename: str, group: str = Config.DEFAULT_GROUP) -> dict | None:
    """Get single image metadata"""
    filepath = Config.UPLOAD_DIR / group / filename
    if not filepath.exists() or not filepath.is_file():
        return None

    ext = filepath.suffix.lower()
    stat = filepath.stat()

    width = height = None
    if ext in Config.PILLOW_FORMATS and HAS_PIL:
        try:
            with Image.open(filepath) as img:
                width, height = img.size
        except Exception:
            pass

    created_dt = datetime.fromtimestamp(stat.st_ctime)

    return {
        'filename': filename,
        'group': group,
        'url': url_for('serve_upload', group=group, filename=filename),
        'absolute_path': str(filepath.resolve()),
        'size': stat.st_size,
        'formatted_size': format_size(stat.st_size),
        'created': created_dt.isoformat(),
        'created_formatted': created_dt.strftime('%Y-%m-%d %H:%M'),
    }


def scan_images(group: str = Config.DEFAULT_GROUP) -> list[dict]:
    """Scan group directory, return images sorted by newest first"""
    group_dir = Config.UPLOAD_DIR / group
    if not group_dir.exists():
        return []

    images = []
    for f in sorted(group_dir.iterdir(),
                     key=lambda p: p.stat().st_ctime, reverse=True):
        if f.is_file() and allowed_file(f.name):
            info = get_image_info(f.name, group)
            if info:
                images.append(info)
    return images


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
