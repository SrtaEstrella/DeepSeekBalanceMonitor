import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import src.config
mac_dir = Path.home() / "Library" / "Application Support" / src.config.APP_NAME
mac_dir.mkdir(parents=True, exist_ok=True)
src.config.CONFIG_DIR = mac_dir
src.config.CONFIG_FILE = mac_dir / "config.json"
src.config.LOG_FILE = mac_dir / "app.log"

from src.config import load_config, save_config, T
from src.mac.keystore import encrypt_api_key, decrypt_api_key

# ─── Eye icon (SVG-style drawn on Canvas) ─────────────────────────────────────
_EYE_OPEN = (
    "M8 5C4.5 5 1.5 8 1.5 8S4.5 11 8 11 14.5 8 14.5 8 11.5 5 8 5z "
    "M8 10a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
)
_EYE_CLOSED = (
    "M2 2 L14 14 M8 5C4.5 5 1.5 8 1.5 8S4.5 11 8 11 14.5 8 14.5 8"
)

def _make_eye_button(parent, entry_widget, show_var: tk.BooleanVar):
    """Draw an eye icon on a Canvas that toggles password visibility."""
    BTN = 28
    c = tk.Canvas(parent, width=BTN, height=BTN, highlightthickness=0,
                  cursor="hand2")
    # ttk widgets don't support "bg"; use systemWindowBackgroundColor for native look
    try:
        c.configure(bg="systemWindowBackgroundColor")
    except Exception:
        c.configure(bg="white")

    def _redraw():
        c.delete("all")
        closed = show_var.get()
        # Use a color that works in both light and dark modes
        color = "#A0A0A0" if closed else "#707070"
        # If in dark mode (detected by bg), flip or adjust? 
        # Actually, let's just use one clear color
        color = "gray" 
        
        # Draw eye outline
        if not closed:
            c.create_oval(5, 9, 23, 19, outline=color, width=1.5, fill="")
            c.create_oval(11, 11, 17, 17, outline=color, width=1.5, fill="")
        else:
            c.create_arc(5, 6, 23, 22, start=20, extent=140, outline=color, width=1.5, style="arc")
            c.create_line(8, 18, 11, 14, fill=color, width=1.5)
            c.create_line(14, 12, 14, 9, fill=color, width=1.5)
            c.create_line(20, 18, 17, 14, fill=color, width=1.5)
            c.create_line(4, 22, 10, 16, fill=color, width=1.5, capstyle="round")
            c.create_line(18, 12, 24, 6, fill=color, width=1.5, capstyle="round")

    def _toggle(_event=None):
        show_var.set(not show_var.get())
        entry_widget.config(show="" if show_var.get() else "•")
        _redraw()

    c.bind("<Button-1>", _toggle)
    _redraw()
    return c


def run_settings():
    config = load_config()
    lang = config.get("language", "zh")
    CTRL_W = 18  # uniform width for all controls (in text units)

    root = tk.Tk()
    root.title(T("settings_title", lang))
    root.resizable(False, False)

    root.lift()
    root.attributes('-topmost', True)
    root.after_idle(root.attributes, '-topmost', False)
    root.focus_force()

    style = ttk.Style()
    # On macOS, 'aqua' is the native theme and usually the only one that supports dark mode well
    try:
        style.theme_use('aqua')
    except Exception:
        pass

    # Use system colors for best macOS native look/dark mode support
    bg_color = "systemWindowBackgroundColor"
    fg_color = "systemTextColor"
    
    root.configure(bg=bg_color)
    
    style.configure("TFrame", background=bg_color)
    style.configure("TLabel", font=("system", 13), background=bg_color, foreground=fg_color)
    style.configure("TCheckbutton", font=("system", 13), background=bg_color, foreground=fg_color)
    style.configure("Title.TLabel", font=("system", 24, "bold"), background=bg_color, foreground=fg_color)
    
    # Standardize Button padding and look
    style.configure("TButton", font=("system", 13))
    
    # Fix Combobox background in some macOS versions
    style.map("TCombobox", fieldbackground=[("readonly", "systemTextBackgroundColor")])

    # ── Header ────────────────────────────────────────────────────────────────
    header = ttk.Frame(root)
    header.pack(fill="x", pady=(24, 16), padx=30)
    banner_sub = "配置您的账号与预警偏好。" if lang == "zh" else "Configure your account and monitor preferences."
    ttk.Label(header, text="DeepSeek Balance", style="Title.TLabel").pack(anchor="w")
    ttk.Label(header, text=banner_sub, foreground="gray", font=("system", 12)).pack(anchor="w")

    # ── Content ───────────────────────────────────────────────────────────────
    content = ttk.Frame(root)
    content.pack(fill="both", expand=True, padx=30)

    # API Key row: Entry + eye-icon button side-by-side
    ttk.Label(content, text=T("api_key_label", lang)).pack(anchor="w")

    decrypted_key = decrypt_api_key(config.get("api_key_enc", ""), mac_dir)
    if not decrypted_key:
        decrypted_key = config.get("api_key", "")  # migrate plain-text legacy

    api_var = tk.StringVar(value=decrypted_key)
    show_var = tk.BooleanVar(value=False)

    key_frame = ttk.Frame(content)
    key_frame.pack(anchor="w", pady=(4, 12), fill="x")

    api_entry = ttk.Entry(key_frame, textvariable=api_var, show="•",
                          width=CTRL_W, font=("system", 14))
    api_entry.pack(side="left")

    eye_btn = _make_eye_button(key_frame, api_entry, show_var)
    eye_btn.pack(side="left", padx=(8, 0))

    # ── Grid of controls ──────────────────────────────────────────────────────
    grid_frame = ttk.Frame(content)
    grid_frame.pack(fill="x", pady=4)
    # Column 0: labels (natural width), Column 1: controls (fixed 180px)
    grid_frame.columnconfigure(0, weight=0)
    grid_frame.columnconfigure(1, weight=0, minsize=180)

    def _label(row, text):
        ttk.Label(grid_frame, text=text).grid(row=row, column=0, sticky="w", pady=8, padx=(0,12))

    def _spinbox(row, var, **kw):
        # Force a fixed width to ensure alignment with Combobox
        sb = ttk.Spinbox(grid_frame, textvariable=var, font=("system", 13), width=CTRL_W - 2, **kw)
        sb.grid(row=row, column=1, sticky="w", padx=(0, 0))
        return sb

    def _combo(row, var, values):
        cb = ttk.Combobox(grid_frame, textvariable=var, values=values,
                          state="readonly", font=("system", 13), width=CTRL_W - 2)
        cb.grid(row=row, column=1, sticky="w", padx=(0, 0))
        return cb

    _label(0, T("interval_label", lang))
    interval_var = tk.IntVar(value=config.get("interval_minutes", 10))
    _spinbox(0, interval_var, from_=1, to=1440)

    _label(1, T("threshold_label", lang))
    threshold_var = tk.DoubleVar(value=config.get("threshold_yuan", 1.0))
    _spinbox(1, threshold_var, from_=0.0, to=10000.0, increment=0.5)

    _label(2, T("language_label", lang))
    LANG_OPTIONS = {"中文": "zh", "English": "en"}
    cur_lang = {v: k for k, v in LANG_OPTIONS.items()}.get(config.get("language", "zh"), "中文")
    lang_var = tk.StringVar(value=cur_lang)
    _combo(2, lang_var, list(LANG_OPTIONS.keys()))

    _label(3, T("currency", lang) + " / Currency:")
    CUR_OPTIONS = ["CNY", "USD"]
    cur_var = tk.StringVar(value=config.get("currency", "CNY"))
    _combo(3, cur_var, CUR_OPTIONS)

    enable_alerts_var = tk.BooleanVar(value=config.get("enable_alerts", True))
    ttk.Checkbutton(content, text=T("enable_alerts_label", lang),
                    variable=enable_alerts_var).pack(anchor="w", pady=(12, 4))

    # ── Buttons ───────────────────────────────────────────────────────────────
    btn_frame = ttk.Frame(root)
    btn_frame.pack(fill="x", pady=(12, 20), padx=30)

    def on_save():
        key = api_var.get().strip()
        if not key:
            messagebox.showwarning(T("warn_title", lang), T("warn_no_key", lang), parent=root)
            return
        config["api_key_enc"] = encrypt_api_key(key, mac_dir)
        config.pop("api_key", None)           # remove any legacy plain-text
        config["interval_minutes"] = interval_var.get()
        config["threshold_yuan"] = threshold_var.get()
        config["language"] = LANG_OPTIONS.get(lang_var.get(), "zh")
        config["currency"] = cur_var.get()
        config["enable_alerts"] = enable_alerts_var.get()
        save_config(config)
        root.destroy()

    def _cleanup():
        root.destroy()

    save_btn = ttk.Button(btn_frame, text=T("save", lang), command=on_save, default="active")
    save_btn.pack(side="right", padx=(10, 0))
    ttk.Button(btn_frame, text=T("cancel", lang), command=_cleanup).pack(side="right")

    root.bind("<Return>", lambda e: save_btn.invoke())
    root.bind("<Escape>", lambda e: _cleanup())
    api_entry.focus_set()
    root.mainloop()


if __name__ == "__main__":
    run_settings()
