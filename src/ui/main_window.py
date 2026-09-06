"""
Main window — unified Notebook with History / Settings / Dev tabs.
Windows-only; mac keeps its own webview/tk fallback.
Single instance: tray clicks always reuse the same Toplevel and select the requested tab.
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

from src.core.config import T, log


class MainWindow:
    def __init__(self, app):
        self.app = app
        self._win = None
        self._notebook = None
        self._tabs = {}
        self._win_icon_handles = []

    def _ensure(self):
        if self._win is not None and self._win.winfo_exists():
            return self._win
        root = self.app._tk_root
        win = tk.Toplevel(root)
        self._win = win
        # keep MainWindow instance in app._main_window (set by caller), don't overwrite with Toplevel
        if getattr(self.app, "_main_window", None) is None or isinstance(self.app._main_window, tk.Toplevel):
            self.app._main_window = self
        # keep legacy flags in sync for callers that check them
        self.app._settings_window = win
        self.app._history_window = win

        lang = self.app.lang
        win.title("DSMonitor")
        # Height computed to show EXACTLY two chart blocks + the third block's header.
        # Chart canvases are fixed 210 physical px; headers/paddings scale with DPI
        # (tkk/ttk fonts scale automatically), so only those parts multiply by _scale.
        try:
            _scale = win.winfo_fpixels("1i") / 96.0
        except Exception:
            _scale = 1.0
        _need_h = int((28 + 125 + 10) * _scale + 2 * (30 * _scale + 210) + 30 * _scale + 40)
        win.geometry(f"860x{_need_h}")
        win.minsize(600, 500)
        # center
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{(sw - w)//2}+{(sh - h)//2}")

        # NOTE: no static iconbitmap here. iconbitmap out-prioritizes
        # iconphoto, so it would pin the window to app.ico and hide the
        # dynamic icon; the window instead inherits the Tk default icon set
        # via iconphoto (same crisp rendering as the unsaved-changes dialog).

        # hide on close, with unsaved check
        self._last_tab = "settings"
        def _on_close():
            try:
                sett = self._tabs.get("settings")
                if sett and hasattr(sett, "check_unsaved") and not sett.check_unsaved():
                    return  # user chose not to discard
            except Exception:
                pass  # don't block close on check failure
            try:
                win.withdraw()
            except Exception:
                pass
        win.protocol("WM_DELETE_WINDOW", _on_close)

        nb = ttk.Notebook(win)
        self._notebook = nb
        nb.pack(fill="both", expand=True, padx=6, pady=6)

        # Lazy tab construction: pre-register lightweight holders (keeps tab order
        # stable); each tab's real content builds on FIRST selection — first launch
        # only pays for the initially visible tab, killing the startup jank.
        self._holders = {}    # key -> placeholder frame inside notebook
        self._builders = {}   # key -> callable(parent) -> content widget

        def _register(key, title, builder):
            holder = ttk.Frame(nb)
            nb.add(holder, text=title)
            self._holders[key] = holder
            self._builders[key] = builder

        def _build_manage(parent):
            from src.ui.manage_frame import ManageFrame
            return ManageFrame(parent, self.app, on_change=self._on_api_change)

        def _build_dashboard(parent):
            from src.ui.history_dialog import HistoryFrame
            return HistoryFrame(parent, self.app)

        def _build_settings(parent):
            from src.ui.settings_dialog import SettingsFrame
            return SettingsFrame(parent, self.app, on_save=self._on_settings_saved)

        _register("manage", T("manage", lang), _build_manage)
        _register("history", T("dashboard", lang), _build_dashboard)
        _register("settings", T("settings", lang).rstrip("…"), _build_settings)
        if self.app.demo_mode:
            def _build_dev(parent):
                from src.tray_app import DevFrame
                return DevFrame(parent, self.app)
            _register("dev", T("dev_tools", lang), _build_dev)

        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # start hidden
        win.withdraw()
        return win

    def set_dynamic_icon(self, pil_img):
        """iconphoto is REQUIRED as the Tk baseline (without it the window
        shows Tk's default feather icon), then WM_SETICON overrides both
        slots: BIG ← 256px handle (taskbar), SMALL ← smooth 16px frame.

        Content is deduplicated: if the rendered art hasn't changed we skip
        ALL icon rebuilding, so the taskbar holds one stable handle instead
        of churning (the churn was what made clarity come and go)."""
        win = self._win
        if win is None or not win.winfo_exists():
            return
        try:
            import hashlib
            fp = hashlib.md5(pil_img.tobytes()).hexdigest()
            if fp == getattr(self, "_icon_fp", None):
                return
            self._icon_fp = fp
        except Exception:
            pass
        try:
            from PIL import Image, ImageTk
            # CRITICAL: taskbar big icon — if Tk's iconphoto ever re-applies
            # the window icon, it must be the SAME 256px art as our
            # WM_SETICON BIG handle, otherwise whichever path wins shows a
            # small image upscaled (blur). Same source, same size → crisp
            # either way.
            big = pil_img.resize((256, 256), Image.LANCZOS)
            photo = ImageTk.PhotoImage(big)
            win.iconphoto(True, photo)
            self._dynamic_icon = photo
        except Exception as e:
            from src.core.config import log
            log(f"Window icon (iconphoto) update failed: {e}")
        self._apply_win32_icons(pil_img)
        # Tk re-applies its 256px photo to the small icon during the event
        # pump, so re-inject the smooth 16px SMALL AFTER the loop is idle —
        # the last writer wins for the title bar.
        try:
            self._win.after(0, lambda: self._apply_win32_icons(pil_img, force=True))
        except Exception:
            pass

    def _apply_win32_icons(self, pil_img, force=False):
        """Class-level + window-level icon install with TWO stability rules:
        1) content dedup — if the rendered art is unchanged, do NOT rebuild the
           handles (rebuilding every poll was racing Tk's paint and produced
           the on-again/off-again blur);
        2) delayed destruction — old handles live one extra cycle before
           DestroyIcon so the taskbar never references a freed icon.
        force=True skips the dedup (used for the post-event-loop SMALL
        re-injection)."""
        try:
            import hashlib, io, struct, ctypes
            from PIL import Image
            from src.core.paths import CONFIG_DIR
            fp = hashlib.md5(pil_img.tobytes()).hexdigest()
            if not force and fp == getattr(self, "_icon_fp", None):
                return
            self._icon_fp = fp
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            ico = CONFIG_DIR / "taskbar_icon.ico"
            master = pil_img.resize((256, 256), Image.LANCZOS)
            small16 = pil_img.resize((16, 16), Image.LANCZOS)
            with open(ico, "wb") as f:
                # two frames: 16px (pre-smoothed) + 256px master
                f.write(struct.pack("<HHH", 0, 1, 2))
                entries = []
                for im in (small16, master):
                    b = io.BytesIO()
                    im.save(b, format="PNG")
                    data = b.getvalue()
                    w = im.width if im.width < 256 else 0
                    h = im.height if im.height < 256 else 0
                    entries.append((w, h, data))
                off = 22 + 16 * len(entries)
                for w, h, data in entries:
                    f.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32,
                                        len(data), off))
                    off += len(data)
                for _, _, data in entries:
                    f.write(data)
            user32 = ctypes.windll.user32
            hwnd = self._win.winfo_id()
            h_big = user32.LoadImageW(None, str(ico), 1, 256, 256, 0x10)
            h_sm = user32.LoadImageW(None, str(ico), 1, 16, 16, 0x10)
            if h_big:
                user32.SendMessageW(hwnd, 0x80, 1, h_big)   # ICON_BIG
            if h_sm:
                user32.SendMessageW(hwnd, 0x80, 0, h_sm)    # ICON_SMALL
            if h_big:
                user32.SetClassLongPtrW(hwnd, -14, h_big)   # GCLP_HICON
            if h_sm:
                user32.SetClassLongPtrW(hwnd, -34, h_sm)    # GCLP_HICONSM
            # retire handles from two generations ago
            for old in getattr(self, "_win_icon_pending", []):
                try:
                    user32.DestroyIcon(old)
                except Exception:
                    pass
            self._win_icon_pending = getattr(self, "_win_icon_handles", [])
            self._win_icon_handles = [h for h in (h_big, h_sm) if h]
        except Exception as e:
            from src.core.config import log
            log(f"Window icon (taskbar) update failed: {e}")

    def _ensure_tab(self, key):
        """Build a registered tab's content on first use. Returns content or None."""
        if key in self._tabs:
            return self._tabs[key]
        builder = self._builders.get(key)
        holder = self._holders.get(key)
        if not builder or not holder:
            return None
        try:
            w = builder(holder)
            w.pack(fill="both", expand=True)
            self._tabs[key] = w
            return w
        except Exception as e:
            log(f"Failed to build {key} tab: {e}")
            return None

    def _on_tab_changed(self, e):
        """NotebookTabChanged: lazy-build target tab, then on_show/refresh."""
        try:
            sel = self._notebook.select()
            holder = self._notebook.nametowidget(sel)
            new_tab = None
            for k, h in self._holders.items():
                if h is holder:
                    new_tab = k
                    break
            self._last_tab = new_tab
            w = self._ensure_tab(new_tab)
            if w is not None:
                if hasattr(w, "on_show"):
                    w.on_show()
                if hasattr(w, "refresh"):
                    w.refresh()
        except Exception as e:
            log(f"Tab change failed: {e}")

    def show(self, tab="manage"):
        win = self._ensure()
        # tray items map directly to tab keys; unknown → first tab
        tab_map = {"api_management": "manage", "manage": "manage", "history": "history", "dashboard": "history", "ledger": "manage", "settings": "settings", "dev": "dev", "apis": "manage"}
        key = tab_map.get(tab, tab)
        if key not in self._holders:
            # fallback to first registered tab
            key = next(iter(self._holders), None)
        if key:
            try:
                w = self._ensure_tab(key)
                self._notebook.select(self._holders[key])
                if w is not None:
                    if hasattr(w, "on_show"):
                        w.on_show()
                    if hasattr(w, "refresh"):
                        w.refresh()
            except Exception:
                pass
        try:
            win.deiconify()
            win.lift()
            # window just became visible: push the current status icon so the
            # title bar / taskbar don't sit on the static .ico until the next poll
            try:
                from src.tray_app import _update_icons
                _update_icons(self.app)
            except Exception:
                pass
            win.after(50, win.focus_force)
        except Exception:
            pass
        # deterministically pre-build remaining tabs AFTER first paint — but one tab
        # per tick (chained), so no single callback blocks the UI long enough to jank
        def _prebuild_next():
            for k in self._holders:
                if k not in self._tabs:
                    self._ensure_tab(k)
                    try:
                        w = self._tabs.get(k)
                        if w is not None and hasattr(w, "on_show"):
                            w.on_show()
                    except Exception:
                        pass
                    # schedule the NEXT tab build on a later tick
                    win.after(350, _prebuild_next)
                    return
        win.after(200, _prebuild_next)

    def _leave_settings_check(self):
        """If settings has unsaved changes, prompt save/discard.
        Returns False when the user cancels (stay on settings)."""
        sett = self._tabs.get("settings")
        if not sett or not hasattr(sett, "check_unsaved"):
            return True
        try:
            if getattr(sett, "_dirty", False):
                return sett.check_unsaved()
        except Exception:
            pass
        return True

    def hide(self):
        if not self._leave_settings_check():
            return  # user cancelled — stay on settings, keep window open
        if self._win and self._win.winfo_exists():
            try:
                self._win.withdraw()
            except Exception:
                pass

    def close_for_rebuild(self):
        """Tear down the window + all lazy tab state so the next show() rebuilds
        from scratch (used after a language switch — widgets can't re-i18n live)."""
        try:
            if self._win and self._win.winfo_exists():
                self._win.destroy()
        except Exception:
            pass
        self._win = None
        self._tabs.clear()
        self._holders.clear()
        self._builders.clear()

    def _on_api_change(self):
        # called when APIs added/edited/deleted — refresh OTHER tabs.
        # NOTE: do not touch manage.mgmt here — mgmt.refresh() invokes on_change,
        # which would recurse (mgmt → on_change → mgmt → …)
        try:
            hist = self._tabs.get("history")
            if hist and hasattr(hist, "refresh_api_selector"):
                hist.refresh_api_selector()
        except Exception:
            pass
        try:
            sett = self._tabs.get("settings")
            if sett and hasattr(sett, "refresh_preferred_selector"):
                sett.refresh_preferred_selector()
        except Exception:
            pass
        try:
            from src.ui.icon_renderer import create_icon_image
            if self.app.icon:
                self.app.icon.icon = create_icon_image(self.app)
                if hasattr(self.app, "_rebuild_menu"):
                    self.app.icon.menu = self.app._rebuild_menu()
        except Exception:
            pass

    def _on_settings_saved(self):
        # called from SettingsFrame after successful save — refresh tray and history
        try:
            from src.ui.icon_renderer import create_icon_image
            if self.app.icon:
                self.app.icon.icon = create_icon_image(self.app)
                if hasattr(self.app, "_rebuild_menu"):
                    self.app.icon.menu = self.app._rebuild_menu()
        except Exception:
            pass
        # also refresh api management and history selectors (preferred may have changed)
        try:
            self._on_api_change()
        except Exception:
            pass
        # dashboard should follow the newly-saved preferred API
        try:
            self.refresh_all(follow_preferred=True)
        except Exception:
            pass

    def refresh_all(self, follow_preferred=False):
        for w in self._tabs.values():
            try:
                if hasattr(w, "refresh"):
                    w.refresh(follow_preferred=follow_preferred)
            except Exception:
                pass
