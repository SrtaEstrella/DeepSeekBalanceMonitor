"""
History viewer — paginated balance records, trend chart, consumption rate, CSV export.
"""
import csv as _csv
import os
import sys as _sys
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from src.core.config import T, load_config, get_apis, get_api_by_id, format_ago
from src.platforms.registry import get_all_platforms as _get_plats, get_platform, billing_col as BILLING_COL_MAP_REF, STATUS_ICON as _STATUS_ICON_SHARED
from src.core.storage import export_all_csv, export_package_csv, get_consumption_rate, get_history_by_date, get_history_page, get_package_history_page
from src.core.paths import DB_FILE
import sqlite3

def _connect_db():
    return sqlite3.connect(str(DB_FILE))

_PLAT_META = _get_plats()

STATUS_SHORT = {
    "none": "OK", "minor": "Min", "major": "Maj",
    "critical": "Crit", "maintenance": "Mnt",
}


class HistoryFrame(ttk.Frame):
    """Embeddable history viewer for MainWindow Notebook."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.lang = app.lang
        self._offset = [0]
        self._rows = []
        self._build()

    def _build(self):
        lang = self.lang
        # API selector
        api_bar = ttk.Frame(self)
        api_bar.pack(fill="x", padx=10, pady=(6, 0))
        ttk.Label(api_bar, text=T("select_api", lang)).pack(side="left")
        self.api_var = tk.StringVar()
        self.api_combo = ttk.Combobox(api_bar, textvariable=self.api_var, state="readonly", width=22)
        self.api_combo.pack(side="left", padx=(6, 0))
        self.api_combo.bind("<<ComboboxSelected>>", lambda e: self._on_api_selected())
        # right-side action buttons (same logic as tray menu)
        ttk.Button(api_bar, text=T("check_now", lang), command=self._manual_check).pack(side="right", padx=(6, 0))
        ttk.Button(api_bar, text=T("top_up", lang), command=self._open_console).pack(side="right")
        self._api_id_map = {}
        self._refresh_api_selector()

        # Info bar — Text widget in a FIXED-PIXEL-height holder (hard height, per spec).
        # Height must be scaled by display DPI: fonts render larger on HiDPI, a raw
        # pixel constant would clip content (150% screen needs ~1.5x the pixels).
        try:
            _dpi_scale = self.winfo_fpixels("1i") / 96.0
        except Exception:
            _dpi_scale = 1.0
        info_holder = tk.Frame(self, height=max(120, int(125 * _dpi_scale)))
        info_holder.pack(fill="x", padx=14, pady=(4, 0))
        info_holder.pack_propagate(False)
        self.info_text = tk.Text(info_holder, relief="flat", bd=0, highlightthickness=0,
                                 wrap="word", takefocus=0, cursor="arrow",
                                 font=("Microsoft YaHei UI", 11),
                                 spacing3=4, padx=4, pady=2)
        self.info_text.tag_configure("big", font=("Microsoft YaHei UI", 14, "bold"))
        self.info_text.tag_configure("normal", font=("Microsoft YaHei UI", 11), foreground="#444")
        # later-created tags have higher priority; ensure big wins for font overlap
        self.info_text.tag_raise("big")
        # no tab stops — bar rows measure the widest label at render time and pack
        # label+bar inside each embedded holder so bars align with zero dead space
        try:
            self.info_text.configure(tabs="")
        except Exception:
            pass
        # progress-bar styles for package quota display — ttk requires
        # "<name>.Horizontal.TProgressbar" naming to inherit the default layout.
        # Fill = remaining%%; color by remaining (<=20%% red, <=60%% amber, else green)
        style = ttk.Style()
        for name, color in (("ok", "#2e7d32"), ("warn", "#e6a23c"), ("crit", "#d93025")):
            style.configure(f"{name}.Horizontal.TProgressbar", troughcolor="#e0e0e0",
                            background=color, thickness=10)
        self._info_windows = []  # embedded widgets alive in the Text; destroyed each render
        self.info_text.configure(state="disabled", background=self.winfo_toplevel().cget("background"))
        self.info_text.pack(fill="both", expand=True)
        # Separator between info bar and chart section
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(6, 0))

        # Chart section — scrollable, three stacked chart blocks (fixed height each)
        chart_scroll = tk.Canvas(self, highlightthickness=0)
        chart_scroll.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(4, 10))
        vsb = ttk.Scrollbar(self, orient="vertical", command=chart_scroll.yview)
        vsb.pack(side="right", fill="y", padx=(0, 8), pady=(4, 10))
        chart_scroll.configure(yscrollcommand=vsb.set)
        inner = ttk.Frame(chart_scroll)
        _win_id = chart_scroll.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: chart_scroll.configure(scrollregion=chart_scroll.bbox("all")))
        def _on_chart_wheel(e):
            try:
                chart_scroll.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        chart_scroll.bind("<Enter>", lambda e: chart_scroll.bind_all("<MouseWheel>", _on_chart_wheel))
        chart_scroll.bind("<Leave>", lambda e: chart_scroll.unbind_all("<MouseWheel>"))
        self._chart_scroll = chart_scroll

        self._charts = {}
        self._chart_vars = {}
        # chart canvases are FIXED physical-pixel height: drawings use pixel coords
        # and their 7pt labels scale via tk's font scaling, so no manual DPI math here.
        self._chart_canvas_h = 210

        def _add_block(key, title, options, default):
            """options: list of (val, label_text); returns (var, canvas)."""
            block = ttk.Frame(inner)
            block.pack(fill="x", pady=(2, 6))
            head = ttk.Frame(block)
            head.pack(fill="x")
            ttk.Label(head, text=title).pack(side="left")  # default font
            var = tk.StringVar(value=default)
            for val, label in options:
                ttk.Radiobutton(head, text=label, variable=var, value=val,
                                command=self._redraw_chart).pack(side="right", padx=(6, 0))
            canvas = tk.Canvas(block, height=self._chart_canvas_h, bg="#f5f5f5", highlightthickness=0)
            canvas.pack(fill="x")
            canvas.bind("<Configure>", lambda e, c=canvas: self._draw_block(key, c))
            # hover tooltip: floating label, hidden until the mouse nears a data point
            canvas._hover_pts = []
            canvas._hover_tt = tk.Label(canvas, bg="#ffffe0", fg="#222", relief="solid",
                                        borderwidth=1, font=("Segoe UI", 8))
            canvas.bind("<Motion>", self._on_chart_hover)
            canvas.bind("<Leave>", lambda e: canvas._hover_tt.place_forget())
            self._charts[key] = canvas
            self._chart_vars[key] = var
            return var, canvas

        _add_block("bal", T("block_balance", lang), [("30d_bal", T("days_30", lang)), ("7d_bal", T("days_7", lang))], "30d_bal")
        _add_block("daily", T("block_daily", lang), [("180d_heat", T("days_180", lang)), ("30d_daily", T("days_30", lang))], "180d_heat")
        _add_block("dist", T("block_dist", lang), [("30d_hourly", T("days_30", lang)), ("7d_hourly", T("days_7", lang))], "30d_hourly")

        # give inner frame the scroll canvas width
        def _sync_inner_width(_e=None):
            try:
                chart_scroll.itemconfigure(_win_id, width=chart_scroll.winfo_width())
            except Exception:
                pass
        chart_scroll.bind("<Configure>", _sync_inner_width)
        _sync_inner_width()

        self._on_api_selected()

    def _draw_block(self, key, canvas):
        """Draw ONE chart block onto a given canvas (called by <Configure>/radios)."""
        api_id = self._get_selected_api_id()
        is_pkg = (self._current_mode == "package")
        chart_type = self._chart_vars.get(key, tk.StringVar(value="")).get()
        kw = dict(canvas=canvas, chart_h=self._chart_canvas_h)
        try:
            canvas._hover_pts = []  # reset hover data for this render
        except Exception:
            pass
        try:
            if key == "bal":
                self._draw_balance_line(chart_type, api_id, is_package=is_pkg, **kw)
            elif key == "daily":
                if chart_type == "180d_heat":
                    if is_pkg:
                        self._draw_heatmap(api_id, days=180, table="package_history",
                                           value_col=self._get_billing_col(api_id), invert=True, **kw)
                    else:
                        self._draw_heatmap(api_id, days=180, table="balance_history",
                                           value_col="topped", **kw)
                elif is_pkg:
                    self._draw_package_daily(api_id, days=30, **kw)
                else:
                    self._draw_daily_consumption(api_id, days=30, **kw)
            elif key == "dist":
                if chart_type == "7d_hourly":
                    if is_pkg:
                        self._draw_package_hourly(api_id, days=7, **kw)
                    else:
                        self._draw_hourly_distribution(api_id, days=7, **kw)
                elif is_pkg:
                    self._draw_package_hourly(api_id, days=30, **kw)
                else:
                    self._draw_hourly_distribution(api_id, days=30, **kw)
        except Exception as e:
            from src.core.config import log
            log(f"Chart block {key} failed: {e}")

    def _redraw_chart(self):
        """Redraw every chart block."""
        for key, canvas in self._charts.items():
            try:
                self._draw_block(key, canvas)
            except Exception as e:
                from src.core.config import log
                log(f"Chart redraw {key} failed: {e}")

    def _on_chart_hover(self, e):
        """Show a floating tooltip near the mouse when it is close to a drawn point."""
        c = e.widget
        pts = getattr(c, "_hover_pts", None)
        if not pts:
            return
        x, y = e.x, e.y
        best = None
        for item in pts:
            if len(item) == 5:            # rect region (x0, y0, x1, y1, text)
                x0, y0, x1, y1, text = item
                # expand hit area slightly; bars with 0 height still hittable
                pad = 4
                if (x0 - pad) <= x <= (x1 + pad) and min(y0, y1) - pad <= y <= max(y0, y1) + pad:
                    best = text
                    break
            else:                          # point (x, y, text)
                px, py, text = item
                d = (px - x) ** 2 + (py - y) ** 2
                if d < 14 * 14:
                    best = text
        tt = getattr(c, "_hover_tt", None)
        if tt is None:
            return
        if best is not None:
            tt.configure(text=best)
            # keep the tooltip inside the canvas: flip left/up when near edges
            cw = c.winfo_width(); chh = c.winfo_height()
            tt.update_idletasks()
            tw, th = tt.winfo_reqwidth(), tt.winfo_reqheight()
            tx = x + 14
            if tx + tw > cw - 4:
                tx = x - 14 - tw
            ty = y + 12
            if ty + th > chh - 4:
                ty = y - 12 - th
            if ty < 2: ty = 2
            tt.place(x=max(2, tx), y=max(2, ty), anchor="nw")
            tt.lift()
        else:
            tt.place_forget()

    def _get_selected_api_id(self):
        name = self.api_var.get()
        return self._api_id_map.get(name, "")

    def _get_selected_platform(self):
        api_id = self._get_selected_api_id()
        api = get_api_by_id(api_id) if api_id else None
        return api.get("platform", "") if api else ""

    def _refresh_api_selector(self, follow_preferred=False):
        # repopulate api combobox from config
        displays = []
        try:
            cfg = load_config()
            apis = get_apis(cfg)
                        # build display -> id map
            self._api_id_map.clear()
            for api in apis:
                disp = api.get("name", "") or "API"
                # dedupe same-name APIs (no platform annotation in display)
                base, n = disp, 2
                while disp in self._api_id_map:
                    disp = f"{base} #{n}"; n += 1
                displays.append(disp)
                self._api_id_map[disp] = api.get("id", "")
            self.api_combo["values"] = displays
        except Exception as e:
            from src.core.config import log
            log(f"refresh_api_selector failed: {e}")
        # normal refresh: preserve valid manual selection;
        # after a preferred switch: always follow the preferred API
        cur = self.api_var.get()
        if follow_preferred or cur not in displays:
            pref_disp = ""
            try:
                cfg = load_config()
                pref = cfg.get("preferred_api_id", "")
                pref_disp = next((d for d, aid in self._api_id_map.items() if aid == pref), "")
            except Exception:
                pass
            self.api_var.set(pref_disp or (displays[0] if displays else ""))

    def _on_api_selected(self):
        """Dashboard: only update mode + redraw chart + rate. No table operations."""
        api_id = self._get_selected_api_id()
        mode = "payg"
        if api_id:
            try:
                api = get_api_by_id(api_id)
                if api:
                    mode = api.get("mode", "payg")
            except Exception:
                pass
        self._current_mode = mode
        self._update_info()
        try:
            self._redraw_chart()
        except Exception:
            pass

    def refresh_api_selector(self, follow_preferred=False):
        self._refresh_api_selector(follow_preferred=follow_preferred)
        self._on_api_selected()

    def _update_info(self):
        """Populate the info bar for the currently SELECTED API."""
        try:
            self._update_info_impl()
        except Exception as e:
            from src.core.config import log
            log(f"Info bar update failed: {e}")
            try:
                self._render_info([T("not_enough_data", self.app.lang)])
            except Exception:
                pass

    def _update_info_impl(self):
        """Populate the info bar for the currently SELECTED API."""
        lang = self.app.lang
        lines = []
        api_id = self._get_selected_api_id()
        api_name = ""
        api_mode = "payg"
        billing_period = "monthly"

        # find selected API info
        cfg = load_config()
        for api in cfg.get("apis") or []:
            if api.get("id") == api_id:
                api_name = api.get("name", "")
                api_mode = api.get("mode", "payg")
                # billing_period is a per-API setting set at creation — take
                # the user's value verbatim, no platform fallback here
                billing_period = api.get("billing_period") or ""
                break

        # read per-API cached data
        with self.app._lock:
            cached = dict(self.app._api_cache.get(api_id, {}))

        balances = cached.get("balances", {})
        pd = cached.get("package_data")
        err = cached.get("error")
        last = cached.get("last_check")
        st = cached.get("service_status")

        # fallback to global state if cache is empty and this is the preferred API
        if not any([balances, pd, err, last]):
            pref_id = self.app.config.get("preferred_api_id", "")
            if api_id == pref_id:
                with self.app._lock:
                    balances = dict(self.app.balances)
                    pd = self.app.package_data
                    err = self.app.error
                    last = self.app.last_check
                    st = self.app.service_status

        _STATUS_ICON = _STATUS_ICON_SHARED

        if api_mode == "package":
            # Package mode info
            if pd is None:
                # fetch failed or not yet checked — show error plus whatever history can provide
                if err:
                    lines.append(f"⚠ {T('bal_error_msg', lang, error=err)}")
                else:
                    lines.append(f"⏳ {T('bal_empty_msg', lang)}")
                dc = self._calc_package_daily_consumption(api_id)
                if dc:
                    today, avg30 = dc
                    if lang == "zh":
                        lines.append(f"⚡ 今日消耗 {today:.2f}%  |  近30天日均消耗 {avg30:.2f}%")
                    else:
                        lines.append(f"⚡ Today {today:.2f}%  |  30d avg {avg30:.2f}%")
                pmeta0 = get_platform(self._get_selected_platform())
                if pmeta0 and pmeta0.has_status_page and st:
                    ind = st.get("indicator") if st else None
                    skey = f"status_{ind}" if ind else "status_unknown"
                    lines.append(f"📡 {T('service_status', lang)} {_STATUS_ICON.get(ind, '⚪')} {T(skey, lang)}")
            else:
                pmeta = get_platform(self._get_selected_platform())
                windows = pmeta.package_windows if pmeta else ["5h", "weekly", "monthly"]
                window_keys = {"5h": ("5h", "rolling"), "weekly": ("weekly",), "monthly": ("monthly",)}
                window_labels = {"5h": T("win_5h", lang), "weekly": T("win_weekly", lang), "monthly": T("win_monthly", lang)}
                for wkey in windows:
                    label = window_labels.get(wkey, wkey)
                    wdata = None
                    for k in window_keys.get(wkey, (wkey,)):
                        wdata = pd.get(k)
                        if wdata:
                            break
                    if wdata:
                        remaining = wdata.get("percent_remaining", 100 - wdata.get("usage_percent", 0))
                        fine = False
                        if wkey in ("weekly", "monthly"):
                            from src.core.storage import get_refined_remaining
                            r = get_refined_remaining(api_id, target=wkey)
                            if r is not None:
                                remaining, fine = r, True
                        reset_s = wdata.get("reset_in_sec", 0)
                        from src.platforms.opencode import format_reset_short
                        reset_str = format_reset_short(reset_s, lang) if reset_s > 0 else "-"
                        line_suffix = T("remaining_pct_fine" if fine else "remaining_pct",
                                        lang, pct=remaining)
                        lines.append({"bar": True, "label": f"{label} ", "pct": remaining,
                                      "suffix": f" {line_suffix}（{reset_str}）"})
                # daily consumption line (from package percent changes) — above rate line
                dc = self._calc_package_daily_consumption(api_id)
                if dc:
                    today, avg30 = dc
                    if lang == "zh":
                        lines.append(f"⚡ 今日消耗 {today:.2f}%  |  近30天日均消耗 {avg30:.2f}%")
                    else:
                        lines.append(f"⚡ Today {today:.2f}%  |  30d avg {avg30:.2f}%")
                if pmeta and pmeta.has_status_page and st:
                    ind = st.get("indicator") if st else None
                    skey = f"status_{ind}" if ind else "status_unknown"
                    lines.append(f"📡 {T('service_status', lang)} {_STATUS_ICON.get(ind, '⚪')} {T(skey, lang)}")
        else:
            # PayG mode info
            if err:
                lines.append(f"⚠ {T('bal_error_msg', lang, error=err)}")
            elif not balances:
                lines.append(f"⏳ {T('bal_empty_msg', lang)}")
            else:
                # balances structure: {currency_code: {total_balance, topped_up_balance, granted_balance}}
                code = "CNY" if "CNY" in balances else next(iter(balances), None)
                pb = balances.get(code) if code else None
                if pb:
                    head = f"{pb['total_balance']:,.2f} {code}"
                    bal_tail = T('bal_line', lang, balance=head.split(" ")[0], code=code,
                                 topped=f"{pb['topped_up_balance']:,.2f}", granted=f"{pb['granted_balance']:,.2f}")
                    # strip duplicated "{balance} {code}" head from template, keep （充值…） tail
                    tail = bal_tail[len(head):] if bal_tail.startswith(head) else bal_tail
                    big_part = f"💰 {head}"
                    lines.append((big_part + tail, len(big_part)))
                    # daily consumption line
                    dc = self._calc_daily_consumption(api_id)
                    if dc:
                        today, avg30 = dc
                        if lang == "zh":
                            lines.append(f"⚡ 今日消耗 {today:.2f}  |  近30天日均消耗 {avg30:.2f}")
                        else:
                            lines.append(f"⚡ Today {today:.2f}  |  30d avg {avg30:.2f}")
                hourly_rate = busy_hours = None
                if not (api_mode == "package"):
                    cr = get_consumption_rate(api_id=api_id) if api_id else get_consumption_rate()
                    if cr: hourly_rate, busy_hours = cr[:2]
                if hourly_rate is not None:
                    total_hrs = round(busy_hours, 1)
                    lines.append(f"📊 {T('rate_line', lang, rate=hourly_rate, prefix=T('est_prefix', lang), remaining=f'{total_hrs}')}")
            ind = st.get("indicator") if st else None
            skey = f"status_{ind}" if ind else "status_unknown"
            lines.append(f"📡 {T('service_status', lang)} {_STATUS_ICON.get(ind, '⚪')} {T(skey, lang)}")

        if last:
            sp = " " if lang == "en" else ""
            lines.append(f"🕐 {T('last_check', lang)}{sp}{format_ago(last, lang)}")

        self._render_info(lines)

    def _render_info(self, lines):
        """Render info lines into the Text widget.
        Supported items: str | (text, big_prefix_len) | {"bar":True,label,pct,suffix}.
        Segments inserted with tags directly (no index arithmetic — safe with emoji)."""
        # destroy previously embedded widgets, then rebuild
        for w in self._info_windows:
            try:
                w.destroy()
            except Exception:
                pass
        self._info_windows = []
        self.info_text.configure(state="normal")
        self.info_text.delete("1.0", "end")

        # measure widest bar label once → uniform label column, bars align exactly
        try:
            _s = self.winfo_fpixels("1i") / 96.0
        except Exception:
            _s = 1.0
        bg0 = self.info_text.cget("background")
        bar_labels = [it["label"].strip() for it in lines if isinstance(it, dict) and it.get("bar")]
        col_w = 0
        if bar_labels:
            probe = tk.Label(self.info_text, text=max(bar_labels, key=len),
                             font=("Microsoft YaHei UI", 11))
            col_w = probe.winfo_reqwidth()
            probe.destroy()
        bar_len_px = int(118 * _s)
        row_h = max(14, int(18 * _s))

        for item in lines:
            if isinstance(item, dict) and item.get("bar"):
                label, pct, suffix = item["label"], float(item.get("pct", 0)), item.get("suffix", "")
                pct = max(0.0, min(100.0, pct))
                # color by remaining (<=20 red / <=60 amber / else green)
                style_name = "crit.Horizontal.TProgressbar" if pct <= 20 else (
                    "warn.Horizontal.TProgressbar" if pct <= 60 else "ok.Horizontal.TProgressbar")
                bg = bg0
                holder_w = col_w + bar_len_px + int(10 * _s)
                holder = tk.Frame(self.info_text, width=holder_w, height=row_h, background=bg)
                holder.pack_propagate(False)
                tk.Label(holder, text=label.strip(), background=bg, fg="#444",
                         font=("Microsoft YaHei UI", 11), anchor="w"
                         ).place(x=0, rely=0.5, anchor="w")
                bar = ttk.Progressbar(holder, style=style_name, orient="horizontal",
                                      length=bar_len_px, mode="determinate", maximum=100.0)
                bar.place(x=col_w + int(4 * _s), rely=0.5, anchor="w")
                bar.configure(value=pct)
                self._info_windows.append(holder)
                self.info_text.window_create("end", window=holder)
                self.info_text.insert("end", suffix + "\n", ("normal",))
            elif isinstance(item, tuple):
                text, big_len = item
                if big_len > 0:
                    self.info_text.insert("end", text[:big_len], ("normal", "big"))
                    self.info_text.insert("end", text[big_len:] + "\n", ("normal",))
                else:
                    self.info_text.insert("end", text + "\n", ("normal",))
            else:
                self.info_text.insert("end", item + "\n", ("normal",))
        # height is fixed by the pixel-height holder; just re-disable editing
        self.info_text.configure(state="disabled")

    def _manual_check(self):
        """Same as tray 立即查询: run a full balance check, then refresh dashboard UI."""
        import threading
        from src.tray_app import do_balance_check

        def _run():
            do_balance_check(self.app)
            # schedule UI refresh on the tk main thread
            try:
                root = self.winfo_toplevel()
                root.after(0, self._on_api_selected)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _open_console(self):
        """Same as tray 控制台: open the selected API's console URL."""
        import webbrowser
        try:
            pmeta = get_platform(self._get_selected_platform())
            url = pmeta.console_url if pmeta else ""
        except Exception:
            url = ""
        webbrowser.open(url or "https://platform.deepseek.com")

    def _calc_daily_consumption(self, api_id):
        """Calculate today's consumption and 30d daily average (busy-period drops).
        Returns (today, avg_30d) or None."""
        try:
            from collections import defaultdict
            rows = self._query_range("balance_history", ["timestamp", "topped"], 30, api_id)
            if len(rows) < 2:
                return None
            daily = defaultdict(float)
            for i in range(1, len(rows)):
                drop = rows[i-1][1] - rows[i][1]
                if drop > 0:
                    daily[rows[i][0][:10]] += drop
            today_str = datetime.now().strftime("%Y-%m-%d")
            today = daily.get(today_str, 0)
            # average over days that had data (up to 30)
            avg = sum(daily.values()) / max(len(daily), 1) if daily else 0
            return round(today, 2), round(avg, 2)
        except Exception:
            return None

    def _calc_package_daily_consumption(self, api_id):
        """Today's quota consumption and 30d daily average, from the refined
        model (fine shape, anchored to the window's observed rise) so the info
        bar matches the charts. Returns (today, avg_30d) or None."""
        try:
            from src.core.storage import get_refined_daily_consumption
            api = get_api_by_id(api_id) if api_id else None
            bp = (api or {}).get("billing_period") or "monthly"
            _labels, vals, _src = get_refined_daily_consumption(api_id, days=30, target=bp)
            if not any(vals):
                return None
            today_str = datetime.now().strftime("%m-%d")
            today = 0.0
            for lbl, v in zip(_labels, vals):
                if lbl == today_str:
                    today = v
            nonz = [v for v in vals if v > 0]
            avg = sum(vals) / max(len(vals), 1)
            return round(today, 2), round(avg, 2)
        except Exception:
            return None

    def _query_range(self, table, cols, days, api_id):
        """Query records from the given table within N days."""
        conn = _connect_db()
        col_str = ", ".join(cols)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            f"SELECT {col_str} FROM {table} WHERE api_id=? AND timestamp >= ? ORDER BY timestamp ASC",
            (api_id or "", cutoff),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def _draw_heatmap(self, api_id, days=180, table="balance_history", value_col="topped", invert=False, canvas=None, chart_h=None):
        """GitHub-style daily-consumption heatmap: one column per week (Mon first row),
        5 shade levels by relative amount. Works for payg (drops) and package (rises)."""
        from collections import defaultdict
        chart = canvas if canvas is not None else getattr(self, "chart", None)
        if chart is None:
            return
        lang = self.app.lang
        rows = self._query_range(table, ["timestamp", value_col], days, api_id)
        # per-day consumption: for package (invert), use the refined model
        # (fine 5h/→weekly shape anchored to the window's observed rise);
        # for payg, consecutive positive drops.
        daily = defaultdict(float)
        if invert:
            from src.core.storage import get_refined_daily_consumption
            api = get_api_by_id(api_id) if api_id else None
            bp = (api or {}).get("billing_period") or "monthly"
            _d0 = datetime.now() - timedelta(days=days - 1)
            _dat, _vals, _src = get_refined_daily_consumption(api_id, days=days, target=bp)
            for i, v in enumerate(_vals):
                if v > 0:
                    daily[(_d0 + timedelta(days=i)).strftime("%Y-%m-%d")] += v
        else:
            if len(rows) < 2:
                return
            for i in range(1, len(rows)):
                prev_v, cur_v = rows[i-1][1] or 0, rows[i][1] or 0
                delta = (cur_v - prev_v) if invert else (prev_v - cur_v)
                if delta > 0:
                    daily[rows[i][0][:10]] += delta

        today = datetime.now().date()
        start = today - timedelta(days=days - 1)
        # align start to Monday so each column is a clean Mon..Sun week
        start -= timedelta(days=start.weekday())

        vals = [daily.get((start + timedelta(days=i)).strftime("%Y-%m-%d"), 0.0)
                for i in range((today - start).days + 1)]
        vmax = max(vals) if vals else 0
        if vmax <= 0:
            return

        def shade(v):
            """5-level green ramp like GitHub."""
            r = v / vmax
            if v <= 0:          return "#ebedf0"
            if r < 0.25:        return "#9be9a8"
            if r < 0.5:         return "#40c463"
            if r < 0.75:        return "#30a14e"
            return "#216e39"

        chart.delete("all")
        cw = chart.winfo_width()
        ch = chart_h or max(getattr(self, "chart_h", 210), chart.winfo_height())
        if cw < 50 or ch < 50:
            chart.after(80, lambda: self._draw_heatmap(api_id, days, table, value_col, invert, chart, ch)); return
        # canvas has a FIXED height; fill it vertically with 7 rows, small margins.
        ml, mr = 46, 8
        mt, mb = 24, 6
        gap = 3
        cell = max(6, min(26, (ch - mt - mb - 6 * gap) // 7))
        step = cell + gap
        rows_h = 7 * cell + 6 * gap
        # center the 7-row block vertically inside the canvas
        mt += (ch - mt - mb - rows_h) // 2

        weeks_total = ((today - start).days // 7) + 1
        block_w = weeks_total * step - gap
        ml_eff = max(ml, (cw - mr - ml - block_w) // 2 + ml)

        # month segments first: [ [month, first_col, last_col], ... ]
        months = []
        d = start; ci = 0
        while d <= today:
            m = d.month
            if months and months[-1][0] == m:
                months[-1][2] = ci
            else:
                months.append([m, ci, ci])
            d += timedelta(days=7); ci += 1

        # weekday labels hug the grid's left edge (small gap)
        zh_wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        en_wd = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        wd_names = zh_wd if lang == "zh" else en_wd
        for r in (0, 2, 4, 6):
            y = mt + r * step + cell / 2
            chart.create_text(ml_eff - 6, y, text=wd_names[r], anchor="e",
                              fill="#666", font=("Segoe UI", 7))

        # month labels with small gap above the grid; skip first month if ~1 week
        month_names = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"] \
            if lang == "zh" else ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        top_gap = mt - 12
        for k, (m, c0, c1) in enumerate(months):
            if k == 0 and (c1 - c0 + 1) <= 1:
                continue
            x = ml_eff + c0 * step
            chart.create_text(x, top_gap, text=month_names[m - 1], anchor="w",
                              fill="#666", font=("Segoe UI", 7))

        # cells: column = week index, row = weekday (Mon=0)
        hover = []
        d = start
        while d <= today:
            wk = (d - start).days // 7
            wd = d.weekday()
            key = d.strftime("%Y-%m-%d")
            v = daily.get(key, 0.0)
            x = ml_eff + wk * step
            y = mt + wd * step
            chart.create_rectangle(x, y, x + cell, y + cell,
                                   fill=shade(v), outline="", width=0)
            hover.append((x, y, x + cell, y + cell,
                          f"{key}  {v:.2f}"))
            d += timedelta(days=1)
        try:
            chart._hover_pts = hover
        except Exception:
            pass

    def _draw_line(self, labels, vals, y_fmt="{:.1f}", color="#3C6966", canvas=None, chart_h=None):
        """Generic line chart renderer. Fills live canvas height."""
        chart = canvas if canvas is not None else getattr(self, "chart", None)
        if chart is None:
            return
        chart.delete("all")
        cw = chart.winfo_width()
        ch = chart_h or max(getattr(self, "chart_h", 210), chart.winfo_height())
        if cw < 50 or ch < 50:
            chart.after(80, lambda: self._draw_line(labels, vals, y_fmt, color, chart, ch)); return
        if len(vals) < 2:
            return
        ml, mr, mt, mb = 50, 12, 16, 28
        w = cw - ml - mr
        h = ch - mt - mb
        lo, hi = min(vals), max(vals)
        if hi == lo: hi = lo + 1
        chart.create_line(ml, mt, ml, mt + h, fill="#999", width=1)
        chart.create_line(ml, mt + h, ml + w, mt + h, fill="#999", width=1)
        # 5 y-axis ticks (whole number + %; hover keeps the precise y_fmt)
        for k in range(5):
            pct = k / 4
            v = lo + (hi - lo) * pct
            y = mt + h * (1 - pct)
            tick = f"{v:.0f}" + ("%" if "%" in y_fmt else "")
            chart.create_text(ml - 6, y, text=tick, anchor="e", fill="#666", font=("Segoe UI", 7))
        n = len(labels)
        # x-axis labels: denser, evenly spaced
        n_x = min(n, 8)
        if n_x >= 2:
            for k in range(n_x):
                idx = round(k * (n - 1) / (n_x - 1))
                x = ml + w * idx / max(n - 1, 1)
                anchor = "nw" if k == 0 else ("ne" if k == n_x - 1 else "n")
                chart.create_text(x, mt + h + 6, text=str(labels[idx]), anchor=anchor, fill="#666", font=("Segoe UI", 7))
        pts = []
        hover = []
        for i, v in enumerate(vals):
            x = ml + w * i / max(n - 1, 1)
            y = mt + h * (1 - (v - lo) / (hi - lo))
            pts.extend((x, y))
            hover.append((x, y, f"{labels[i]}  {y_fmt.format(v)}"))
        try:
            chart._hover_pts = hover
        except Exception:
            pass
        if len(pts) >= 4:
            chart.create_line(pts, fill=color, width=2, smooth=True)
            for x, y in zip(pts[::2], pts[1::2]):
                chart.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline="")

    def _draw_bar(self, labels, vals, y_fmt="{:.0f}", color="#3C6966", canvas=None, chart_h=None):
        """Generic bar chart renderer. Fills live canvas height."""
        chart = canvas if canvas is not None else getattr(self, "chart", None)
        if chart is None:
            return
        chart.delete("all")
        cw = chart.winfo_width()
        ch = chart_h or max(getattr(self, "chart_h", 210), chart.winfo_height())
        if cw < 50 or ch < 50:
            chart.after(80, lambda: self._draw_bar(labels, vals, y_fmt, color, chart, ch)); return
        if not vals:
            return
        ml, mr, mt, mb = 50, 12, 16, 28
        w = cw - ml - mr
        h = ch - mt - mb
        hi = max(max(vals), 0.001)  # draw grid even when all zeros
        chart.create_line(ml, mt, ml, mt + h, fill="#999", width=1)
        chart.create_line(ml, mt + h, ml + w, mt + h, fill="#999", width=1)
        for pct in (0.5, 1):
            v = hi * pct
            y = mt + h * (1 - pct)
            # axis ticks: whole-number + % (hover keeps the precise y_fmt)
            tick = f"{v:.0f}" + ("%" if "%" in y_fmt else "")
            chart.create_text(ml - 6, y, text=tick, anchor="e", fill="#666", font=("Segoe UI", 7))
        bw = max(w / len(vals) - 2, 4)
        hover = []
        for i, v in enumerate(vals):
            x = ml + w * i / len(vals) + 1
            bh = h * v / hi
            chart.create_rectangle(x, mt + h - bh, x + bw, mt + h, fill=color, outline="")
            # rect hit region spanning full column height so thin/zero bars stay hittable
            hover.append((x - 2, mt, x + bw + 2, mt + h,
                          f"{labels[i]}  {y_fmt.format(v)}"))
        try:
            chart._hover_pts = hover
        except Exception:
            pass
        step = max(1, len(labels) // 6)  # sparser x labels (MM-DD is wide)
        for i in range(0, len(labels), step):
            x = ml + w * (i + 0.5) / len(vals)
            chart.create_text(x, mt + h + 6, text=labels[i], anchor="n", fill="#666", font=("Segoe UI", 7))

    def _draw_balance_line(self, chart_type, api_id, is_package=False, canvas=None, chart_h=None):
        """Draw balance line over 7d or 30d."""
        days = 7 if "7d" in chart_type else 30
        lang = self.app.lang
        if is_package:
            billing_period = "monthly"
            try:
                api = get_api_by_id(api_id) if api_id else None
                if api:
                    billing_period = api.get("billing_period") or ""
            except Exception:
                pass
            from src.core.storage import get_refined_remaining_series
            rts, rvs = get_refined_remaining_series(api_id, target=billing_period or "monthly",
                                                    days=days)
            if not rvs:
                self._wipe_chart(canvas)
                return
            labels = [t[5:10] for t in rts]  # MM-DD
            vals = rvs
            self._draw_line(labels, vals, canvas=canvas, chart_h=chart_h,
                            y_fmt="{:.2f}%")
        else:
            rows = self._query_range("balance_history", ["timestamp", "total"], days, api_id)
            labels = [r[0][5:10] for r in rows]  # MM-DD
            vals = [r[1] for r in rows]
            self._draw_line(labels, vals, canvas=canvas, chart_h=chart_h)

    def _wipe_chart(self, canvas):
        """Clear a chart canvas; used on no-data paths so a stale chart
        (e.g. the heatmap) doesn't linger after a view switch."""
        chart = canvas if canvas is not None else getattr(self, "chart", None)
        if chart is not None:
            try:
                chart.delete("all")
            except Exception:
                pass

    def _draw_daily_consumption(self, api_id, days=30, canvas=None, chart_h=None):
        """Draw daily consumption bar chart. Each day = sum of busy-period drops."""
        from collections import defaultdict
        rows = self._query_range("balance_history", ["timestamp", "topped"], days, api_id)
        if len(rows) < 2:
            self._wipe_chart(canvas)
            return
        daily = defaultdict(float)
        for i in range(1, len(rows)):
            drop = rows[i-1][1] - rows[i][1]
            if drop > 0:
                daily[rows[i][0][:10]] += drop
        # generate all days in range, fill 0 for missing
        labels = []
        vals = []
        d = datetime.now() - timedelta(days=days-1)
        for i in range(days):
            day = (d + timedelta(days=i)).strftime("%Y-%m-%d")
            labels.append(day[5:10])  # MM-DD
            vals.append(round(daily.get(day, 0), 2))
        self._draw_bar(labels, vals, y_fmt="{:.1f}", canvas=canvas, chart_h=chart_h)

    def _draw_hourly_distribution(self, api_id, days=7, canvas=None, chart_h=None):
        """Draw hourly distribution bar chart. Bin by hour of day, sum consumption per bin."""
        from collections import defaultdict
        rows = self._query_range("balance_history", ["timestamp", "topped"], days, api_id)
        if len(rows) < 2:
            self._wipe_chart(canvas)
            return
        hourly = defaultdict(float)
        for i in range(1, len(rows)):
            drop = rows[i-1][1] - rows[i][1]
            if drop > 0:
                hour = int(rows[i][0][11:13])
                hourly[hour] += drop
        labels = [f"{h:02d}:00" for h in range(24)]
        vals = [hourly.get(h, 0) for h in range(24)]
        self._draw_bar(labels, vals, y_fmt="{:.1f}", canvas=canvas, chart_h=chart_h)

    def _get_billing_col(self, api_id):
        """Get the package_history column for this API's configured billing
        period (user-set at creation; no platform fallback)."""
        billing_period = ""
        try:
            api = get_api_by_id(api_id) if api_id else None
            if api:
                billing_period = api.get("billing_period") or ""
        except Exception:
            pass
        from src.platforms.registry import billing_col
        return billing_col(billing_period)

    def _draw_package_daily(self, api_id, days=30, canvas=None, chart_h=None):
        """Draw daily quota consumption bar chart, refined: the target window's
        coarse 1%-steps are distributed with a finer window's consumption
        shape (5h → weekly → raw fallback), total anchored to the target's
        observed rise."""
        from src.core.storage import get_refined_daily_consumption
        api = get_api_by_id(api_id) if api_id else None
        bp = (api or {}).get("billing_period") or "monthly"
        labels, vals, _src = get_refined_daily_consumption(
            api_id, days=days, target=bp)
        if not any(vals):
            self._wipe_chart(canvas)
            return
        self._draw_bar(labels, vals, y_fmt="{:.2f}%", canvas=canvas, chart_h=chart_h)

    def _draw_package_hourly(self, api_id, days=7, canvas=None, chart_h=None):
        """Draw hourly distribution of quota consumption, refined by the finest
        window's shape (5h deltas, weekly fallback)."""
        from src.core.storage import get_refined_hourly_distribution
        labels, vals, _src = get_refined_hourly_distribution(api_id, days=days)
        if not any(vals):
            self._wipe_chart(canvas)
            return
        self._draw_bar(labels, vals, y_fmt="{:.2f}%", canvas=canvas, chart_h=chart_h)

    def on_show(self):
        self._refresh_api_selector(follow_preferred=True)
        self._on_api_selected()
        # canvases may be unmapped during first build (winfo_width()==1); kick a redraw
        # once they are mapped and have their real widths
        try:
            self._chart_scroll.after(80, self._redraw_chart)
        except Exception:
            pass

    def refresh(self, follow_preferred=False):
        self._refresh_api_selector(follow_preferred=follow_preferred)
        self._on_api_selected()


class LedgerFrame(ttk.Frame):
    """Table + buttons for browsing raw history records.
    show_selector=False embeds without its own dropdown (driven externally via set_api_id)."""
    def __init__(self, parent, app, show_selector=True):
        super().__init__(parent)
        self.app = app
        self.lang = app.lang
        self._offset = [0]
        self._rows = []
        self._show_selector = show_selector
        self._build()

    def _build(self):
        lang = self.lang
        # API selector (optional — omitted when driven by an external table)
        self._api_id_map = {}
        if self._show_selector:
            api_bar = ttk.Frame(self)
            api_bar.pack(fill="x", padx=10, pady=(6, 0))
            ttk.Label(api_bar, text=T("select_api", lang)).pack(side="left")
            self.api_var = tk.StringVar()
            self.api_combo = ttk.Combobox(api_bar, textvariable=self.api_var, state="readonly", width=22)
            self.api_combo.pack(side="left", padx=(6, 0))
            self.api_combo.bind("<<ComboboxSelected>>", lambda e: self._on_api_selected())
            self._refresh_api_selector()

        # Tree
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        style = ttk.Style()
        style.configure("Ledger.Treeview", rowheight=28, font=("Segoe UI", 9))
        self.tree = None
        self._current_mode = "payg"
                # centered placeholder shown when no API is selected (embedded mode);
        # text customizable by the embedding parent via empty_text attr
        self.placeholder = tk.Label(tree_frame, text=getattr(self, "empty_text", "") or T("select_api_prompt", lang),
                                    font=("Microsoft YaHei UI", 10),
                                    fg="#000", bg="#ffffff")
        self.tree_frame = tree_frame

        # Bottom buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", side="bottom", padx=10, pady=10)
        self.load_btn = ttk.Button(btn_frame, text=T("load_more", lang), command=self._load_page)
        self.load_btn.pack(side="left")
        self.export_btn = ttk.Button(btn_frame, text=T("export_csv_btn", lang), command=self._export_csv)
        self.export_btn.pack(side="left", padx=(6, 0))
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", padx=8, fill="y")
        self.PLACEHOLDER = "YYYYMMDD"
        self.date_var = tk.StringVar(value=self.PLACEHOLDER)
        self.date_entry = ttk.Entry(btn_frame, textvariable=self.date_var, width=10)
        self.date_entry.configure(foreground="gray")
        self.date_entry.bind("<FocusIn>", self._on_date_focus)
        self.date_entry.bind("<FocusOut>", self._on_date_blur)
        self.date_entry.pack(side="left", padx=(8, 4))
        self.query_btn = ttk.Button(btn_frame, text=T("filter_btn", lang), width=6, command=self._query_by_date)
        self.query_btn.pack(side="left")
        self.reset_btn = ttk.Button(btn_frame, text=T("cancel_btn", lang), width=6, command=self._reset_query)
        self.reset_btn.pack(side="left", padx=(4, 0))
        self.reset_btn.configure(state="disabled")

        self._on_api_selected()

    def _on_date_focus(self, e):
        if self.date_var.get() == self.PLACEHOLDER:
            self.date_var.set("")
            self.date_entry.configure(foreground="black")

    def _on_date_blur(self, e):
        if self.date_var.get() == "":
            self.date_var.set(self.PLACEHOLDER)
            self.date_entry.configure(foreground="gray")

    def _get_selected_api_id(self):
        # embedded mode: external driver sets this directly
        if not self._show_selector:
            return getattr(self, "_ext_api_id", "") or ""
        return self._api_id_map.get(self.api_var.get(), "")

    def set_api_id(self, api_id):
        """External driver (Manage tab): switch ledger to the given API."""
        self._ext_api_id = api_id or ""
        self._on_api_selected()

    def _get_selected_platform(self):
        api_id = self._get_selected_api_id()
        api = get_api_by_id(api_id) if api_id else None
        return api.get("platform", "") if api else ""

    def _refresh_api_selector(self):
        if not self._show_selector:
            return
        try:
            cfg = load_config()
            apis = get_apis(cfg)
            self._api_id_map.clear()
            displays = []
            for api in apis:
                disp = api.get("name", "") or "API"
                base, n = disp, 2
                while disp in self._api_id_map:
                    disp = f"{base} #{n}"; n += 1
                displays.append(disp)
                self._api_id_map[disp] = api.get("id", "")
            self.api_combo["values"] = displays
            if displays:
                cur = self.api_var.get()
                if cur not in displays:
                    pref = cfg.get("preferred_api_id", "")
                    pref_disp = next((d for d, aid in self._api_id_map.items() if aid == pref), displays[0])
                    self.api_var.set(pref_disp)
        except Exception:
            pass

    def _rebuild_tree(self, mode="payg", pkg_windows=None, has_status=False):
        lang = self.app.lang
        self._current_mode = mode
        if self.tree is not None:
            self.tree.destroy()
            self.tree = None
        for w in self.tree_frame.winfo_children():
            if isinstance(w, tk.Scrollbar):
                w.destroy()
        if mode == "package":
            windows = pkg_windows or ["5h", "weekly", "monthly"]
            window_labels = {"5h": T("col_5h", lang), "weekly": T("col_weekly", lang), "monthly": T("col_monthly", lang)}
            cols = ["time"] + windows
            headings = {"time": T("th_time", lang)}
            widths = {"time": 200}
            for w in windows:
                headings[w] = window_labels[w]
                widths[w] = 120
            if has_status:
                cols.append("status")
                headings["status"] = T("th_status", lang)
                widths["status"] = 90
        else:
            cols = ["time", "curr", "total", "topped", "granted", "status"]
            headings = {"time": T("th_time", lang), "curr": T("th_currency", lang),
                        "total": T("th_total", lang), "topped": T("th_topped", lang),
                        "granted": T("th_granted", lang), "status": T("th_status", lang)}
            widths = {"time": 220, "curr": 60, "total": 100, "topped": 100, "granted": 100, "status": 90}
        self.tree = ttk.Treeview(self.tree_frame, columns=tuple(cols), show="headings", style="Ledger.Treeview")
        pkg_ws = set(pkg_windows) if pkg_windows else set()
        for c in cols:
            self.tree.heading(c, text=headings[c])
            anchor = "center" if c in pkg_ws or c == "status" else ("e" if c != "time" else "w")
            self.tree.column(c, width=widths[c], minwidth=60, anchor=anchor)
        sb = tk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<MouseWheel>", lambda e: self.tree.yview_scroll(int(-1 * (e.delta / 60)), "units"))

    def _on_api_selected(self):
        api_id = self._get_selected_api_id()
        mode = "payg"
        pkg_windows = None
        has_status = False
        if api_id:
            try:
                api = get_api_by_id(api_id)
                if api:
                    mode = api.get("mode", "payg")
                    pmeta = get_platform(api.get("platform", ""))
                    if pmeta:
                        pkg_windows = pmeta.package_windows
                        has_status = pmeta.has_status_page
            except Exception:
                pass
        self._rebuild_tree(mode, pkg_windows, has_status)
        self._offset[0] = 0
        self._rows.clear()
        self.reset_btn.configure(state="disabled")
        self.date_var.set(self.PLACEHOLDER)
        self.date_entry.configure(foreground="gray")
        # embedded mode with no selection: empty tree + centered placeholder,
        # and ALL data controls disabled so stray clicks can't load other APIs' rows
        if not api_id and not self._show_selector:
            for w in (self.load_btn, self.export_btn, self.query_btn):
                try: w.configure(state="disabled")
                except Exception: pass
            try:
                self.date_entry.configure(state="disabled")
                self.placeholder.place(relx=0.5, rely=0.5, anchor="center")
                self.placeholder.lift()
            except Exception:
                pass
            return
        try:
            self.placeholder.place_forget()
        except Exception:
            pass
        for w in (self.load_btn, self.export_btn, self.query_btn):
            try: w.configure(state="normal")
            except Exception: pass
        try:
            self.date_entry.configure(state="normal")
        except Exception:
            pass
        self._load_page()

    def _load_page(self):
        api_id = self._get_selected_api_id()
        # guard: embedded mode without selection must never query (would hit all rows)
        if not api_id and not self._show_selector:
            return
        if self.app.demo_mode:
            rows = self.app._demo_history[self._offset[0]:self._offset[0] + 100]
        elif self._current_mode == "package":
            rows = get_package_history_page(limit=100, offset=self._offset[0], api_id=api_id or None)
        else:
            rows = get_history_page(limit=100, offset=self._offset[0], api_id=api_id or None)
        for r in rows:
            if self._current_mode == "package":
                vals = [r["timestamp"]]
                for c in self.tree["columns"]:
                    if c == "time":
                        continue
                    if c == "status":
                        ss = r.get("service_status")
                        vals.append(STATUS_SHORT.get(ss, ss) if ss else "-")
                        continue
                    col = BILLING_COL_MAP_REF(c, default="")
                    pct = r.get(col, None)
                    vals.append(f"{100 - (pct or 0):.0f}%" if pct is not None else "-")
                self.tree.insert("", "end", values=tuple(vals))
            else:
                s_label = STATUS_SHORT.get(r["service_status"], r["service_status"]) if r.get("service_status") else "-"
                self.tree.insert("", "end", values=(r["timestamp"], r["currency"], f"{r['total']:.2f}", f"{r['topped']:.2f}", f"{r['granted']:.2f}", s_label))
        self._rows.extend(rows)
        self._offset[0] += len(rows)
        if len(rows) < 100:
            self.load_btn.configure(state="disabled", text=T("all_loaded", self.app.lang))
        else:
            self.load_btn.configure(state="normal", text=T("load_more", self.app.lang))

    def _export_csv(self):
        path = self.app.config.get("export_path", "").strip()
        parent = self.winfo_toplevel()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        api_id = self._get_selected_api_id()
        api = get_api_by_id(api_id) if api_id else None
        api_name = (api.get("name", "") if api else "ledger").replace("/", "_") or "ledger"
        initial = f"{api_name}_{ts}.csv"
        if path:
            f = os.path.join(path, initial)
        else:
            f = filedialog.asksaveasfilename(parent=parent, defaultextension=".csv",
                                             filetypes=[("CSV files", "*.csv")], initialfile=initial)
        if not f:
            return
        api_id = self._get_selected_api_id()
        if self._current_mode == "package":
            n = export_package_csv(f, api_id=api_id or None)
        else:
            n = export_all_csv(f, api_id=api_id or None)
        messagebox.showinfo(T("export_csv_btn", self.app.lang), T("export_msg", self.app.lang, n=n), parent=parent)

    def _query_by_date(self):
        d = self.date_var.get().strip()
        if d in ("", self.PLACEHOLDER): return
        if len(d) == 8 and d.isdigit(): d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        self.tree.delete(*self.tree.get_children())
        api_id = self._get_selected_api_id()
        rows = get_history_by_date(d, api_id=api_id or None)
        self._rows.clear(); self._rows.extend(reversed(rows))
        for r in reversed(rows):
            s_label = STATUS_SHORT.get(r["service_status"], r["service_status"]) if r.get("service_status") else "-"
            self.tree.insert("", "end", values=(r["timestamp"], r["currency"], f"{r['total']:.2f}", f"{r['topped']:.2f}", f"{r['granted']:.2f}", s_label))
        self.reset_btn.configure(state="normal")
        self.load_btn.configure(state="disabled")

    def _reset_query(self):
        self.date_var.set(self.PLACEHOLDER); self.date_entry.configure(foreground="gray")
        self.reset_btn.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self._offset[0] = 0; self._rows.clear()
        self._load_page()

    def on_show(self):
        self._on_api_selected()

    def refresh(self, follow_preferred=False):
        pass