import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# --- MAC OS PATH ADAPTATION ---
# Ensure root directory is in sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import src.config
from PIL import Image, ImageDraw, ImageFont
import tempfile
import rumps

try:
    from AppKit import NSImage, NSColor, NSSize
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False

# Colored SF Symbol config for API service status
_STATUS_SYMBOLS = {
    "none":        ("checkmark.circle.fill", (50, 195, 90)),
    "minor":       ("exclamationmark.triangle.fill", (245, 185, 50)),
    "major":       ("xmark.circle.fill", (220, 70, 60)),
    "critical":    ("xmark.circle.fill", (220, 20, 30)),
    "maintenance": ("wrench.circle.fill", (245, 155, 50)),
    "_default":    ("questionmark.circle.fill", (140, 140, 150)),
    "_error":      ("exclamationmark.circle.fill", (185, 70, 60)),
}

from src.config import load_config, save_config, T as _T, log, CONFIG_DIR

# WebView settings sentinel & PID
_SETTINGS_SENTINEL = CONFIG_DIR / ".settings_changed"
_SETTINGS_PID = CONFIG_DIR / "settings.pid"

# --- macOS Local Translations ---
_MAC_T = {
    "zh": {
        "topped_up": "充值余额",
        "granted": "赠送余额",
        "currency": "货币",
        "checking": "查询中…",
        "error_fetch": "查询出错",
        "check_now": "立即查询",
        "top_up": "充值",
        "settings": "设置",
        "quit": "退出",
    },
    "en": {
        "topped_up": "Topped Up",
        "granted": "Granted",
        "currency": "Currency",
        "checking": "Checking…",
        "error_fetch": "Fetch Error",
        "check_now": "Check Now",
        "top_up": "Top Up",
        "settings": "Settings",
        "quit": "Quit",
    }
}

def T(key, lang="zh", **kwargs):
    """Local translation wrapper that falls back to global T."""
    text = _MAC_T.get(lang, _MAC_T["zh"]).get(key)
    if text:
        return text.format(**kwargs) if kwargs else text
    return _T(key, lang, **kwargs)
from src.api_client import fetch_balance, fetch_service_status
from src.icon_renderer import _get_colors, _text_color
from src.mac.keystore import decrypt_api_key
from src.storage import save_balance_record

# macOS system font attempts
import glob
_FONTS = []

# Helper to find font in bundle
def _get_bundle_path(rel_path):
    if getattr(sys, 'frozen', False):
        # PyInstaller _MEIPASS
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        # Inside .app bundle: Contents/Resources/rel_path
        alt_base = os.path.join(os.path.dirname(sys.executable), "..", "Resources")
        paths = [os.path.join(base, rel_path), os.path.join(alt_base, rel_path)]
        for p in paths:
            if os.path.exists(p): return p
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../", rel_path))

local_font = _get_bundle_path("assets/font/ShareTech-Regular.ttf")
if os.path.exists(local_font):
    _FONTS.append(local_font)
else:
    log(f"Warning: Bundled font not found at {local_font}")

# 2. Search user directories
_FONTS += glob.glob(os.path.expanduser("~/Library/Fonts/*Share*Tech*.ttf"))
_FONTS += glob.glob("/Library/Fonts/*Share*Tech*.ttf")

# 3. Fallback to system fonts
_FONTS += [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/SFNS.ttf"
]

def notify_mac(title, message, subtitle=""):
    """Robust notification using AppKit with delegate (to force display) and osascript fallback."""
    success = False
    try:
        from Foundation import NSUserNotification, NSUserNotificationCenter, NSObject
        
        # Define delegate to force notification display even if app is frontmost
        global _notif_delegate
        if '_notif_delegate' not in globals():
            class NotificationDelegate(NSObject):
                def userNotificationCenter_shouldPresentNotification_(self, center, notification):
                    return True
            _notif_delegate = NotificationDelegate.alloc().init()

        notification = NSUserNotification.alloc().init()
        notification.setTitle_(title)
        if subtitle:
            notification.setSubtitle_(subtitle)
        notification.setInformativeText_(message)
        notification.setSoundName_("NSUserNotificationDefaultSoundName")

        center = NSUserNotificationCenter.defaultUserNotificationCenter()
        if center:
            center.setDelegate_(_notif_delegate)
            center.deliverNotification_(notification)
            success = True
            log("Native AppKit notification delivered")
    except Exception as e:
        log(f"Native notification failed: {e}")

    if not success:
        # Fallback to osascript
        try:
            import subprocess
            # osascript display notification doesn't like multiple lines well
            t = title.replace('"', '\\"')
            m = message.replace('\n', '  ').replace('"', '\\"')
            s = subtitle.replace('"', '\\"')
            script = f'display notification "{m}" with title "{t}"'
            if s: script += f' subtitle "{s}"'
            subprocess.run(["osascript", "-e", script], capture_output=True)
            log("Osascript notification triggered")
        except Exception as e:
            log(f"Osascript notification failed: {e}")

def create_mac_icon(label: str, fill_color: tuple, text_color: tuple) -> str:
    """Render a macOS menubar icon with given colors.
    fill_color: RGBA tuple for background.
    text_color: RGBA tuple for label text.
    """
    scale = 4
    base_size = 18
    size = base_size * scale

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin_outer = 1.85 * scale
    radius = 2.75 * scale

    draw.rounded_rectangle([margin_outer, margin_outer, size - margin_outer, size - margin_outer],
                           radius=radius, fill=fill_color)

    font_size = 10 * scale
    font = None
    for fn in _FONTS:
        try:
            font = ImageFont.truetype(fn, font_size)
            font.path = fn
            break
        except Exception:
            continue
    if not font:
        font = ImageFont.load_default()

    margin_inner = 1 * scale
    while hasattr(font, 'getlength') and font.getlength(label) > (size - margin_outer*2 - margin_inner*2) and font_size > 6:
        font_size -= 0.5 * scale
        try:
            font = ImageFont.truetype(font.path, int(font_size))
            font.path = font.path
        except: break

    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), label, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (size - w) / 2 - bbox[0]
        y = (size - h) / 2 - bbox[1]
        draw.text((x, y), label, fill=text_color, font=font)
    else:
        draw.text((size/2, size/2), label, fill=text_color, font=font, anchor="mm")

    final_size = base_size * 2
    img = img.resize((final_size, final_size), Image.Resampling.LANCZOS)

    icon_path = os.path.join(tempfile.gettempdir(), "ds_balance_mac_icon.png")
    img.save(icon_path)
    return icon_path

class DeepSeekBalanceMacApp(rumps.App):
    def __init__(self):
        super(DeepSeekBalanceMacApp, self).__init__("DS Balance", quit_button=None)

        self.config = load_config()
        self.balances = {}
        self.last_check = None
        self.error = None
        self.service_status = None
        self._timer = None
        self._running = True
        self._dirty_ui = False
        self._dirty_menu = False

        # Start sentinel watcher for WebView settings changes
        threading.Thread(target=self._watch_settings_sentinel, daemon=True).start()

        # Build Menus
        self.info_item = rumps.MenuItem("...", callback=None)
        self.detail_topped = rumps.MenuItem("...", callback=self.on_show_balance)
        self.detail_granted = rumps.MenuItem("...", callback=self.on_show_balance)
        self.rate_item = rumps.MenuItem("...", callback=self.on_show_balance)
        self.last_check_item = rumps.MenuItem("...", callback=self.on_show_balance)
        self.api_status_item = rumps.MenuItem("...", callback=lambda _: None)

        self.rebuild_menus()
        self.update_ui()
        self.on_check_now(None)

    @property
    def lang(self):
        return self.config.get("language", "zh")

    def rebuild_menus(self):
        self.menu.clear()
        
        self.info_item = rumps.MenuItem("...", callback=self.on_show_balance)
        self.detail_topped = rumps.MenuItem("...", callback=self.on_show_balance)
        self.detail_granted = rumps.MenuItem("...", callback=self.on_show_balance)
        self.last_check_item = rumps.MenuItem("...", callback=self.on_show_balance)
        self.api_status_item = rumps.MenuItem("...", callback=lambda _: None)

        self.menu.add(self.info_item)
        self.menu.add(self.detail_topped)
        self.menu.add(self.detail_granted)
        self.menu.add(self.rate_item)
        self.menu.add(self.last_check_item)
        self.menu.add(rumps.separator)
        self.menu.add(self.api_status_item)
        self.menu.add(rumps.separator)

        str_check = T("check_now", self.lang)
        str_topup = T("top_up", self.lang)
        str_set = T("settings", self.lang)
        str_quit = T("quit", self.lang)

        btn_check = rumps.MenuItem(str_check, callback=self.on_check_now)
        btn_topup = rumps.MenuItem(str_topup, callback=self.on_top_up)
        btn_set = rumps.MenuItem(str_set, callback=self.on_settings)
        btn_quit = rumps.MenuItem(str_quit, callback=self.on_quit)
        
        # Apply native SF Symbols if PyObjC is available
        if HAS_PYOBJC:
            from AppKit import NSSize
            def _add_sf(item, symbol_name):
                try:
                    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
                    if img:
                        new_img = NSImage.alloc().initWithSize_(NSSize(18, 18))
                        new_img.lockFocus()
                        orig_size = img.size()
                        scale = min(16.0 / orig_size.width, 16.0 / orig_size.height)
                        if scale > 1: scale = 1
                        new_w = orig_size.width * scale
                        new_h = orig_size.height * scale
                        x = (18 - new_w) / 2.0
                        y = (18 - new_h) / 2.0
                        img.drawInRect_(((x, y), (new_w, new_h)))
                        new_img.unlockFocus()
                        new_img.setTemplate_(True)
                        item._menuitem.setImage_(new_img)
                except Exception: pass
            
            _add_sf(btn_check, "arrow.triangle.2.circlepath")
            _add_sf(btn_topup, "creditcard")
            _add_sf(btn_set, "gearshape")
            _add_sf(btn_quit, "xmark.circle")

        self.menu.add(btn_check)
        self.menu.add(btn_topup)
        self.menu.add(btn_set)
        self.menu.add(rumps.separator)
        self.menu.add(btn_quit)

        self.update_ui()

    def get_preferred_balance(self):
        pref_currency = self.config.get("currency", "CNY")
        if pref_currency in self.balances:
            return {**self.balances[pref_currency], "currency": pref_currency}
        for c, b in self.balances.items():
            return {**b, "currency": c}
        return None

    @rumps.timer(0.5)
    def update_ui_timer(self, _):
        # We need to update UI on the main thread. Rumps timers run on main thread.
        if getattr(self, '_dirty_ui', False):
            self.update_ui()
            self._dirty_ui = False
        if getattr(self, '_dirty_menu', False):
            try:
                self.rebuild_menus()
            except Exception as e:
                log(f"Menu rebuild error: {e}")
            self._dirty_menu = False

    def _set_sf_icon(self, item, symbol_name, rgb):
        """Apply a colored SF Symbol as a menu item image."""
        if not HAS_PYOBJC: return
        try:
            from AppKit import NSImage, NSColor, NSImageSymbolConfiguration
            img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol_name, None)
            if not img: return
            
            r, g, b = rgb
            color = NSColor.colorWithDeviceRed_green_blue_alpha_(r/255.0, g/255.0, b/255.0, 1.0)
            
            # Hierarchical coloring (macOS 12.0+)
            try:
                config = NSImageSymbolConfiguration.configurationWithHierarchicalColor_(color)
                colored_img = img.imageByApplyingSymbolConfiguration_(config)
                item._menuitem.setImage_(colored_img)
            except:
                # Fallback to tinting (macOS 10.15+)
                try:
                    colored_img = img.imageWithTintColor_(color)
                    item._menuitem.setImage_(colored_img)
                except:
                    item._menuitem.setImage_(img)
        except Exception as e:
            log(f"SF Symbol Error: {e}")

    def trigger_ui_update(self):
        self._dirty_ui = True

    def update_ui(self):
        label = "..."
        is_error = self.error is not None

        # Determine theme-based colors
        colors = _get_colors(self.config)
        if is_error:
            fill = colors["low"]
            label = "!"
            self.info_item.title = f"{T('error_fetch', self.lang)}: {self.error[:20]}"
            self.detail_topped.title = "  ..."
            self.detail_granted.title = "  ..."
            self.last_check_item.title = "  ..."
        elif not self.balances:
            fill = colors["nodata"]
            label = "..."
            self.info_item.title = T("checking", self.lang)
            self.detail_topped.title = "  ..."
            self.detail_granted.title = "  ..."
            self.last_check_item.title = "  ..."
        else:
            b = self.get_preferred_balance()
            if b:
                val = int(b["total_balance"])
                t = float(self.config.get("threshold_yuan", 1.0))
                is_low = b["total_balance"] < t
                fill = colors["low"] if is_low else colors["ok"]

                if val >= 10000:
                    label = f"{val//1000}k"
                elif val >= 1000:
                    label = f"{val/1000:.1f}k".replace(".0k", "k")
                else:
                    label = str(val)

                last_str = self.last_check.strftime("%Y-%m-%d %H:%M:%S") if self.last_check else "-"
                self.info_item.title = f"{T('total_balance', self.lang)}: {b['total_balance']:.2f} {b['currency']}"
                self.detail_topped.title = f"  {T('topped_up', self.lang)}: {b['topped_up_balance']:.2f}"
                self.detail_granted.title = f"  {T('granted', self.lang)}: {b['granted_balance']:.2f}"
                
                # Update consumption rate
                from src.storage import get_consumption_rate
                cr = get_consumption_rate()
                if cr:
                    daily_rate, hours_left, _curr = cr
                    days = int(hours_left // 24)
                    hrs = int(hours_left % 24)
                    if self.lang == "en":
                        self.rate_item.title = f"  Avg: {daily_rate:.2f}/day | Est: {days}d {hrs}h"
                    else:
                        self.rate_item.title = f"  日均消耗: {daily_rate:.2f} | 预计可用: {days}天 {hrs}小时"
                    self.rate_item.set_callback(self.on_show_balance)
                else:
                    self.rate_item.title = f"  {T('not_enough_data', self.lang)}" if self.lang == "zh" else "  Not enough data"
                    self.rate_item.set_callback(None)

                self.last_check_item.title = f"  {T('last_check', self.lang)}: {last_str}"

        # API status line — colored SF Symbol (or emoji fallback)
        ss = self.service_status
        if ss:
            indicator = str(ss.get("indicator", "unknown")).lower()
            status_text = T(f"status_{indicator}", self.lang)
            if HAS_PYOBJC:
                self.api_status_item.title = status_text
                sym, rgb = _STATUS_SYMBOLS.get(indicator, _STATUS_SYMBOLS["_default"])
                self._set_sf_icon(self.api_status_item, sym, rgb)
            else:
                emoji = {"none": "🟢", "minor": "🟡", "major": "🔴",
                         "critical": "🔴", "maintenance": "🟠"}.get(indicator, "⚪")
                self.api_status_item.title = f"{emoji} {status_text}"
        elif is_error:
            if HAS_PYOBJC:
                self.api_status_item.title = T("status_unknown", self.lang)
                self._set_sf_icon(self.api_status_item, *_STATUS_SYMBOLS["_error"])
            else:
                self.api_status_item.title = f"⚪ {T('status_unknown', self.lang)}"
        else:
            self.api_status_item.title = "..."
            if HAS_PYOBJC:
                self.api_status_item._menuitem.setImage_(None)

        self.template = False
        text_c = _text_color(fill)
        self.icon = create_mac_icon(label, fill, text_c)

    def on_check_now(self, _):
        if self._timer:
            self._timer.cancel()
        self.trigger_ui_update()
        threading.Thread(target=self._do_check, daemon=True).start()

    def on_show_balance(self, _):
        if not self.balances:
            notify_mac(title=T("bal_empty_title", self.lang), message=T("bal_empty_msg", self.lang))
            return
            
        lines = []
        for code, b in self.balances.items():
            lines.append(f"{code}: {b['total_balance']:.2f} (充值: {b['topped_up_balance']:.2f}, 赠送: {b['granted_balance']:.2f})")
        msg = "\n".join(lines)
        
        pb = self.get_preferred_balance()
        title = f"余额详情: {pb['total_balance']:.2f} {pb['currency']}" if pb else "余额详情"
        
        notify_mac(title=title, message=msg)

    def on_top_up(self, _):
        import subprocess
        subprocess.run(["open", "https://platform.deepseek.com/top_up"])

    def _do_check(self):
        # Try encrypted key first, then fall back to legacy plain-text
        api_key = decrypt_api_key(self.config.get("api_key_enc", ""), CONFIG_DIR).strip()
        if not api_key:
            api_key = self.config.get("api_key", "").strip()
        if not api_key:
            self.error = T("error_no_key", self.lang)
            self.balances = {}
        else:
            try:
                data = fetch_balance(api_key)
                self.balances = data["all_balances"]
                self.error = None
                self.last_check = datetime.now()
                try:
                    self.service_status = fetch_service_status()
                except Exception:
                    self.service_status = None
                log("Mac balance check OK")
                
                ss = self.service_status
                s_indicator = ss.get("indicator") if ss else None
                for code, bal in data["all_balances"].items():
                    save_balance_record(code, bal["total_balance"],
                                        bal["topped_up_balance"],
                                        bal["granted_balance"],
                                        service_status=s_indicator)
                log(f"Mac balance saved to DB ({len(data['all_balances'])} records)")
                
                b = self.get_preferred_balance()
                if b and self.config.get("enable_alerts", True):
                    t = float(self.config.get("threshold_yuan", 1.0))
                    if b["total_balance"] < t:
                        notify_mac(
                            title=T("low_bal_title", self.lang),
                            message=f"当前余额仅剩 {b['total_balance']:.2f} {b['currency']}，低于预警阈值！"
                        )
            except Exception as e:
                self.error = str(e).split("\n")[0]
                self.balances = {}
                log(f"Mac check failed: {e}")
                
        self.trigger_ui_update()
        
        interval_min = int(self.config.get("interval_minutes", 10))
        self._timer = threading.Timer(interval_min * 60, self.on_check_now, args=(None,))
        self._timer.daemon = True
        self._timer.start()

    def _try_webview_settings(self):
        """Try to open WebView-based settings. Returns True if successful."""
        # Check if already running — bring to front by re-spawning
        # If PID file exists, the process might still be alive
        if _SETTINGS_PID.exists():
            try:
                pid = int(_SETTINGS_PID.read_text().strip())
                # Check if process is alive (macOS: kill -0)
                os.kill(pid, 0)
                log(f"WebView settings already running (pid {pid})")
                # Bring to front: use AppKit to avoid "System Events" permission prompt
                if HAS_PYOBJC:
                    from AppKit import NSRunningApplication
                    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                    if app:
                        app.activateWithOptions_(3)  # NSApplicationActivateAllWindows(1) | NSApplicationActivateIgnoringOtherApps(2)
                else:
                    subprocess.run(
                        ["osascript", "-e",
                         'tell app "System Events" to set frontmost of '
                         '(first process whose unix id is ' + str(pid) + ') to true'],
                        capture_output=True, timeout=5)
                return True
            except (OSError, ValueError, subprocess.TimeoutExpired):
                # Stale PID file
                _SETTINGS_PID.unlink(missing_ok=True)

        # Launch WebView as subprocess
        try:
            me = sys.executable
            if getattr(sys, "frozen", False):
                args = [me, "--settings-webview"]
            else:
                args = [me, "-m", "src.webview.main"]
            subprocess.Popen(args, start_new_session=True)
            log("WebView settings launched as subprocess")
            return True
        except Exception as e:
            log(f"Failed to launch WebView settings: {e}")
            return False

    def _watch_settings_sentinel(self):
        """Background thread: poll sentinel file to reload config on save."""
        while self._running:
            if _SETTINGS_SENTINEL.exists():
                try:
                    _SETTINGS_SENTINEL.unlink()
                    self.config = load_config()
                    self._dirty_menu = True
                    self.on_check_now(None)
                    log("Settings changed via WebView — config reloaded")
                except Exception as e:
                    log(f"Sentinel handler error: {e}")
            time.sleep(1)

    def on_settings(self, _):
        self._try_webview_settings()
    
    def on_test_notify(self, _):
        notify_mac(
            title=T("low_bal_title", self.lang),
            subtitle="这是一条测试通知",
            message="在余额低于设定的阈值时，程序会自动弹出类似的警告提醒您充值。"
        )

    def on_quit(self, _):
        self._running = False
        if self._timer:
            self._timer.cancel()
        rumps.quit_application()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--settings-webview":
        from src.webview.main import main as webview_main
        webview_main()
        sys.exit(0)

    log("DeepSeek Balance Monitor (Mac version) starting")
    app = DeepSeekBalanceMacApp()
    app.run()
