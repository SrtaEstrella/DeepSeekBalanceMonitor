import os
import sys
import threading
from datetime import datetime
from pathlib import Path

# --- MAC OS PATH ADAPTATION ---
# Monkey-patch config paths before importing deep dependencies
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import src.config
mac_dir = Path.home() / "Library" / "Application Support" / src.config.APP_NAME
mac_dir.mkdir(parents=True, exist_ok=True)
src.config.CONFIG_DIR = mac_dir
src.config.CONFIG_FILE = mac_dir / "config.json"
src.config.LOG_FILE = mac_dir / "app.log"

import rumps
from PIL import Image, ImageDraw, ImageFont
import tempfile

try:
    from AppKit import NSImage
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False

from src.config import load_config, save_config, T, log
from src.api_client import fetch_balance
from src.mac.keystore import decrypt_api_key

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

def create_mac_icon(label: str, is_error: bool, is_low: bool) -> str:
    # Use 4x supersampling for perfect anti-aliasing on Retina displays
    scale = 4
    base_size = 18  # 18pt is standard, but we'll use more padding to make it look smaller
    size = base_size * scale
    
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    fill_color = (60, 105, 102, 255) # Teal
    if is_error or is_low:
        fill_color = (185, 70, 60, 255) # Red
    elif label == "...":
        fill_color = (105, 105, 110, 255) # Gray
        
    # DRAW BOX: Make it smaller than the 18pt canvas (16pt effective)
    # Token Meter uses roughly 2pt margin at top/bottom
    margin_outer = 1.85 * scale 
    radius = 2.75 * scale # Tighter corners like Token Meter
    
    draw.rounded_rectangle([margin_outer, margin_outer, size - margin_outer, size - margin_outer], 
                           radius=radius, fill=fill_color)
    
    # FONT: Make it bold and clear
    font_size = 10 * scale
    font = None
    # Try to find a bold variant of the font if possible
    bold_font_path = _get_bundle_path("assets/font/ShareTech-Regular.ttf") # We only have regular, so we'll rely on size
    
    for fn in _FONTS:
        try:
            font = ImageFont.truetype(fn, font_size)
            font.path = fn 
            break
        except Exception:
            continue
    if not font:
        font = ImageFont.load_default()
        
    # Shrink font if text is too wide
    margin_inner = 1 * scale
    while hasattr(font, 'getlength') and font.getlength(label) > (size - margin_outer*2 - margin_inner*2) and font_size > 6:
        font_size -= 0.5 * scale
        try:
            font = ImageFont.truetype(font.path, int(font_size))
            font.path = font.path
        except: break

    # Center label
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), label, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (size - w) / 2 - bbox[0]
        y = (size - h) / 2 - bbox[1]
        draw.text((x, y), label, fill=(255, 255, 255, 255), font=font)
    else:
        draw.text((size/2, size/2), label, fill=(255, 255, 255, 255), font=font, anchor="mm")
    
    # Save as 2x (36px)
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
        self._timer = None
        
        # Build Menus
        self.info_item = rumps.MenuItem("...", callback=None)
        self.detail_topped = rumps.MenuItem("  充值余额: -", callback=None)
        self.detail_granted = rumps.MenuItem("  赠送余额: -", callback=None)
        self.last_check_item = rumps.MenuItem("  上次查询: -", callback=None)
        
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
        
        self.menu.add(self.info_item)
        self.menu.add(self.detail_topped)
        self.menu.add(self.detail_granted)
        self.menu.add(self.last_check_item)
        self.menu.add(rumps.separator)
        
        # Strip emojis from standard localized strings
        str_check = T("check_now", self.lang).replace("🔄", "").replace("📋", "").strip()
        str_set = T("settings", self.lang).replace("⚙", "").replace("  ", " ").strip()
        str_quit = T("quit", self.lang).replace("❌", "").replace(" ", "").strip()
        
        btn_check = rumps.MenuItem(str_check, callback=self.on_check_now)
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
            _add_sf(btn_set, "gearshape")
            _add_sf(btn_quit, "xmark.circle")
            
        self.menu.add(btn_check)
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

    def trigger_ui_update(self):
        self._dirty_ui = True

    def update_ui(self):
        label = "..."
        is_error = self.error is not None
        is_low = False
        
        if is_error:
            label = "!"
            self.info_item.title = f"{T('error_fetch', self.lang)}: {self.error[:20]}"
            self.detail_topped.title = "  ..."
            self.detail_granted.title = "  ..."
            self.last_check_item.title = "  ..."
        elif not self.balances:
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
                
                # Format large numbers compactly
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
                self.last_check_item.title = f"  {T('last_check', self.lang)}: {last_str}"
                
        # Only use custom colored icon if template is True it gets forced to B&W
        self.template = False 
        self.icon = create_mac_icon(label, is_error, is_low)

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

    def _do_check(self):
        # Try encrypted key first, then fall back to legacy plain-text
        api_key = decrypt_api_key(self.config.get("api_key_enc", ""), mac_dir).strip()
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
                log("Mac balance check OK")
                
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

    def on_settings(self, _):
        import subprocess
        # Pass --settings flag to the executable to avoid duplicate tray icons
        # In bundled app, sys.executable is the app binary itself.
        subprocess.run([sys.executable, "--settings"])
        
        # After settings process closes, reload config and refresh
        self.config = load_config()
        self.rebuild_menus()
        self.on_check_now(None)
        
    def on_test_notify(self, _):
        notify_mac(
            title=T("low_bal_title", self.lang),
            subtitle="这是一条测试通知",
            message="在余额低于设定的阈值时，程序会自动弹出类似的警告提醒您充值。"
        )

    def on_quit(self, _):
        if self._timer:
            self._timer.cancel()
        rumps.quit_application()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--settings":
        from src.mac.settings import run_settings
        run_settings()
        sys.exit(0)

    log("DeepSeek Balance Monitor (Mac version) starting")
    app = DeepSeekBalanceMacApp()
    app.run()
