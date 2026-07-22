"""Shared request helpers for route modules.

These are pure (they depend only on Flask's request/jsonify, Config, and
utils) and never import the Flask app instance, so both app.py and the
route blueprints can import them without a circular dependency.
"""

from functools import wraps

from flask import jsonify, request
from werkzeug.utils import secure_filename

from config import Config
from utils import ensure_group_dirs, is_valid_group_name

# Loopback addresses that count as "the host machine" for admin endpoints.
_LOOPBACK_ADDRS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}


def local_only(f):
    """Reject non-loopback callers with 403.

    The server binds 0.0.0.0 (LAN-reachable), but administrative/destructive
    endpoints must only be driven from the host itself.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.remote_addr not in _LOOPBACK_ADDRS:
            return jsonify({"error": "This action is only allowed from the host machine"}), 403
        return f(*args, **kwargs)

    return wrapper


def with_query_group(f):
    """Inject a validated `group` from the `?group=` query arg.

    Reads `request.args['group']` (defaulting to the default group), returns
    400 if it's not a valid group name, and otherwise passes it to the view
    as the `group` keyword argument.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        group = request.args.get("group", Config.DEFAULT_GROUP)
        if not is_valid_group_name(group):
            return jsonify({"error": "Invalid group name"}), 400
        kwargs["group"] = group
        return f(*args, **kwargs)

    return wrapper


def group_error(name: str):
    """Return a (response, 400) tuple if `name` is an invalid group, else None.

    For groups that arrive somewhere other than the `?group=` query arg
    (request body, target/source group) where the decorator doesn't fit.
    """
    if not is_valid_group_name(name):
        return jsonify({"error": "Invalid group name"}), 400
    return None


def safe_or_error(filename: str, label: str = "filename"):
    """Sanitize a filename. Returns (safe_name, None) or (None, error_response).

    Usage:
        safe, err = safe_or_error(filename)
        if err:
            return err
    """
    safe = secure_filename(filename)
    if not safe:
        return None, (jsonify({"error": f"Invalid {label}"}), 400)
    return safe, None


def get_request_files(group: str):
    """Load and validate uploaded files from the current request.

    Creates the group directories and extracts the file list from
    `request.files`, filtering out empty/unnamed entries.

    Returns ``(files, None)`` on success, or ``(None, error_response)`` on
    failure (missing files key or no valid files after filtering).

    Usage:
        files, err = get_request_files(group)
        if err:
            return err
    """
    ensure_group_dirs(group)

    if "files" not in request.files:
        return None, (jsonify({"error": "No file data in request"}), 400)

    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename and f.filename.strip()]

    if not files:
        return None, (jsonify({"error": "Please select files to upload"}), 400)

    return files, None
