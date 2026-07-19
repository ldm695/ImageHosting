"""Route blueprints for ImageHosting.

Grouped by domain so app.py can stay focused on app setup, settings
persistence, static file serving, and the server lifecycle.
"""

from .groups import bp as groups_bp
from .images import bp as images_bp

ALL_BLUEPRINTS = (groups_bp, images_bp)


def register_blueprints(app):
    """Register every route blueprint on the given Flask app."""
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
