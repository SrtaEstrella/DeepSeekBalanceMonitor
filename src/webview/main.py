"""WebView settings window entry point.

Launched as a subprocess from the macOS tray app.
Run directly: python -m src.webview.main
"""

import os
import sys
import atexit

# Ensure project root is in sys.path (needed when launched as subprocess)
_src_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _src_root not in sys.path:
    sys.path.insert(0, _src_root)


def _get_icon_path():
    """Locate AppIcon.icns (dev or frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.join(
            os.path.dirname(sys.executable), "..", "Resources", "AppIcon.icns"
        )
    return os.path.join(
        os.path.dirname(__file__), "..", "..", "assets", "AppIcon.icns"
    )


def _show_dock_icon():
    """Show dock icon with AppIcon.icns when settings window opens."""
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyRegular, NSImage
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        icon_path = _get_icon_path()
        if os.path.exists(icon_path):
            icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
            if icon:
                NSApp.setApplicationIconImage_(icon)
    except Exception:
        pass


def get_web_dir():
    """Locate web/ directory (dev or frozen)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.join(meipass, "webview", "web")
        return os.path.join(
            os.path.dirname(sys.executable), "..", "Resources", "webview", "web"
        )
    return os.path.join(os.path.dirname(__file__), "web")


def get_web_url():
    web_dir = get_web_dir()
    index = os.path.join(web_dir, "index.html")
    if os.path.exists(index):
        rev = str(int(os.path.getmtime(index)))
        return f"{index}?rev={rev}"
    return "about:blank"


def main():
    import webview
    from .bridge import JsApi

    # Show dock icon with proper app icon
    _show_dock_icon()

    api = JsApi()
    api.save_pid()
    atexit.register(api.cleanup_pid)

    url = get_web_url()
    window = webview.create_window(
        title="DeepSeek Balance Monitor – Settings",
        url=url,
        js_api=api,
        width=860,
        height=680,
        min_size=(640, 480),
        resizable=True,
        background_color="#1c1c1c",
    )
    api.set_window(window)

    webview.start(http_server=True, private_mode=False)


if __name__ == "__main__":
    main()
