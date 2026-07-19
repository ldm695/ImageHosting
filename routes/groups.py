"""Group CRUD routes (create / list / rename / delete)."""

import shutil

from flask import Blueprint, jsonify, request

from config import Config
from helpers import local_only
from utils import ensure_group_dirs, is_valid_group_name, scan_groups

bp = Blueprint("groups", __name__)


@bp.route("/api/groups", methods=["GET"])
def api_list_groups():
    """List all groups"""
    return jsonify(scan_groups())


@bp.route("/api/groups", methods=["POST"])
def api_create_group():
    """Create a new group"""
    data = request.get_json(silent=True) or {}
    name = (data.get("name", "") or "").strip()

    if not name:
        return jsonify({"error": "Group name is required"}), 400
    if not is_valid_group_name(name):
        return jsonify(
            {"error": "Group name can only contain letters, numbers, underscores, and hyphens"}
        ), 400

    group_dir = Config.UPLOAD_DIR / name
    if group_dir.exists():
        return jsonify({"error": f'Group "{name}" already exists'}), 409

    ensure_group_dirs(name)
    return jsonify({"success": True, "name": name}), 201


@bp.route("/api/groups/<name>", methods=["DELETE"])
@local_only
def api_delete_group(name):
    """Delete a group and all its images"""
    if name == Config.DEFAULT_GROUP:
        return jsonify({"error": "Cannot delete the default group"}), 400
    if not is_valid_group_name(name):
        return jsonify({"error": "Invalid group name"}), 400

    group_dir = Config.UPLOAD_DIR / name
    thumb_dir = Config.THUMBNAIL_DIR / name

    if not group_dir.exists():
        return jsonify({"error": "Group not found"}), 404

    try:
        shutil.rmtree(str(group_dir))
        if thumb_dir.exists():
            shutil.rmtree(str(thumb_dir))
    except Exception as e:
        return jsonify({"error": f"Delete failed: {str(e)}"}), 500

    return jsonify({"success": True})


@bp.route("/api/groups/<name>", methods=["PUT"])
def api_rename_group(name):
    """Rename a group"""
    if name == Config.DEFAULT_GROUP:
        return jsonify({"error": "Cannot rename the default group"}), 400

    data = request.get_json(silent=True) or {}
    new_name = (data.get("new_name", "") or "").strip()

    if not new_name:
        return jsonify({"error": "New name is required"}), 400
    if not is_valid_group_name(new_name):
        return jsonify(
            {"error": "Name can only contain letters, numbers, underscores, and hyphens"}
        ), 400

    old_dir = Config.UPLOAD_DIR / name
    new_dir = Config.UPLOAD_DIR / new_name
    if not old_dir.exists():
        return jsonify({"error": "Group not found"}), 404
    if new_dir.exists():
        return jsonify({"error": f'Group "{new_name}" already exists'}), 409

    old_thumb = Config.THUMBNAIL_DIR / name
    new_thumb = Config.THUMBNAIL_DIR / new_name

    try:
        old_dir.rename(new_dir)
        if old_thumb.exists():
            old_thumb.rename(new_thumb)
    except Exception as e:
        return jsonify({"error": f"Rename failed: {str(e)}"}), 500

    return jsonify({"success": True, "name": new_name}), 200
