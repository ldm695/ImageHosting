"""
System tray icon for ImageHosting (Windows).

Provides a notification-area icon with:
  - Open Browser
  - Restart Server
  - Exit
"""
import os
import sys
import json
import time
import webbrowser
import threading
from pathlib import Path

try:
    import pystray
    from pystray import MenuItem as Item
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _create_icon_image() -> 'Image.Image':
    """Generate a 64×64 tray icon (purple circle with IH)."""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer circle
    draw.ellipse([1, 1, size - 2, size - 2], fill=(108, 92, 231, 255))
    # Inner circle (slightly lighter)
    draw.ellipse([8, 8, size - 10, size - 10], fill=(130, 115, 240, 255))
    # Letter "IH"
    try:
        font = ImageFont.truetype("segoeui.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "IH", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1]
    draw.text((tx, ty), "IH", fill="white", font=font)
    return img


def _get_icon():
    """Try to load icon.ico from assets/ or app dir; fall back to generated image."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    for candidate in [base / 'assets' / 'icon.ico', base / 'icon.ico']:
        if candidate.exists() and HAS_PIL:
            return Image.open(candidate)
    return _create_icon_image()


def run_tray(port: int, *, server_stopped: threading.Event = None):
    """
    Create and run the system tray icon (blocking).

    Args:
        port: server port for browser URL
        server_stopped: Event to signal when the server should stop
    """
    if not HAS_TRAY:
        print("pystray not installed — tray icon disabled")
        return

    shutdown_url = f'http://localhost:{port}/api/shutdown'
    open_url = f'http://localhost:{port}'
    stop_flag = server_stopped or threading.Event()

    def action_open():
        webbrowser.open(open_url)

    def action_restart():
        """Send shutdown signal; the main loop in app.py will auto-restart."""
        import urllib.request
        try:
            req = urllib.request.Request(shutdown_url, data=b'{}',
                                         headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

    def action_exit():
        stop_flag.set()
        try:
            import urllib.request
            req = urllib.request.Request(shutdown_url, data=b'{}',
                                         headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass
        # Force exit after a short delay
        time.sleep(0.5)
        os._exit(0)

    menu = (
        Item("Open Browser", action_open, default=True),
        Item("Restart Server", action_restart),
        Item("Exit", action_exit),
    )

    icon = pystray.Icon("ImageHosting", _get_icon(), "ImageHosting", menu)

    # Run the icon (blocking until icon.stop() is called or Exit is clicked)
    icon.run()
