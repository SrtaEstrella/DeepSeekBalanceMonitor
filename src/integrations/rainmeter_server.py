"""
Local Rainmeter HTTP interface — serves widget status on 127.0.0.1:17654.
"""
import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from datetime import datetime

from src.core.config import T, log, get_api_by_id
from src.ui.icon_renderer import _get_colors
from src.core.storage import get_consumption_rate


def _start_server(app):
    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            # No Access-Control-Allow-Origin: the response carries balance and
            # subscription data, and a wildcard would let any page open in the
            # browser read it (or call /check through it). Rainmeter's WebParser
            # does not need CORS — same hardening the Rust builds carry.
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            p = urlparse(self.path)
            qs = parse_qs(p.query)
            lang = qs.get("lang", ["en"])[0]

            if p.path == "/check":
                app._trigger_check()

            if p.path in ("/widget-status", "/check"):
                with app._lock:
                    b = app.get_preferred_balance()
                    err = app.error
                    st = app.service_status
                    last = app.last_check

                # accent_color: R,G,B
                colors = _get_colors(app.config)
                rgb = colors["ok"]
                accent_color = f"{rgb[0]},{rgb[1]},{rgb[2]}"

                # balance_line
                if err:
                    balance_line = T("tooltip_error", lang, error=err)
                elif b:
                    balance_line = f"💰 {b['total_balance']:,.2f} {b['currency']}"
                else:
                    balance_line = "💰 -- CNY"

                # status_line
                if err:
                    status_line = T("bal_error_msg", lang, error=err)
                elif b is None:
                    status_line = T("bal_empty_msg", lang)
                else:
                    status_line = f"{T('total_balance', lang)}: {b['total_balance']:,.2f} {b['currency']}"

                # last_check
                if last:
                    diff = datetime.now() - last
                    mins = int(diff.total_seconds() / 60)
                    if mins < 1:
                        ago = T("ago_just", lang)
                    elif mins < 60:
                        ago = T("ago_min", lang, n=mins)
                    else:
                        hrs = mins // 60
                        ago = T("ago_hr", lang, n=hrs)
                else:
                    ago = T("not_checked", lang)

                # service_status_line
                indicator = st.get("indicator") if st else None
                key = f"status_{indicator}" if indicator else "status_unknown"
                service_status_line = T(key, lang)

                # estimated_line — for preferred API (package mode has no rate)
                pref_id = app.config.get("preferred_api_id")
                cr = None
                try:
                    pref_api = get_api_by_id(pref_id) if pref_id else None
                    if not (pref_api and pref_api.get("mode") == "package"):
                        cr = get_consumption_rate(api_id=pref_id) if pref_id else get_consumption_rate()
                except Exception as e:
                    from src.core.paths import log
                    log(f"Rainmeter rate lookup failed: {e}")
                if cr and b:
                    hourly_rate, busy_hours, _curr = cr
                    days = int(busy_hours // 24)
                    hrs = int(busy_hours % 24)
                    if days > 0:
                        remaining = T("remaining_dh", lang, d=days, h=hrs)
                    elif hrs >= 1:
                        remaining = T("remaining_h", lang, h=hrs)
                    else:
                        remaining = T("remaining_lt1h", lang)
                    prefix = T("est_prefix", lang)
                    estimated_line = f"📊 {prefix} {remaining}"
                else:
                    estimated_line = T("rms_fallback", lang)

                self._respond({
                    "accent_color": accent_color,
                    "balance_line": balance_line,
                    "status_line": status_line,
                    "last_check": ago,
                    "service_status_line": service_status_line,
                    "estimated_line": estimated_line,
                })
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 17654), _Handler)
    log("Rainmeter server started on 127.0.0.1:17654")
    server.serve_forever()


def start_rainmeter_server(app):
    t = threading.Thread(target=_start_server, args=(app,), daemon=True)
    t.start()
