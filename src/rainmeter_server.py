"""
Local Rainmeter HTTP interface — serves widget status on 127.0.0.1:17654.
"""
import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from src.config import log


def _start_server(app):
    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            p = urlparse(self.path)
            qs = parse_qs(p.query)
            lang = qs.get("lang", ["en"])[0]

            if p.path == "/check":
                from src.tray_app import do_balance_check
                do_balance_check(app)

            if p.path in ("/widget-status", "/check"):
                with app._lock:
                    b = app.get_preferred_balance()
                    err = app.error
                    st = app.service_status
                    last = app.last_check

                from src.config import T
                from src.icon_renderer import _get_colors

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
                    from datetime import datetime
                    diff = datetime.now() - last
                    mins = int(diff.total_seconds() / 60)
                    if mins < 1:
                        ago = "just now" if lang == "en" else "刚刚"
                    elif mins < 60:
                        ago = f"{mins} min ago" if lang == "en" else f"{mins} 分钟前"
                    else:
                        hrs = mins // 60
                        ago = f"{hrs} hr ago" if lang == "en" else f"{hrs} 小时前"
                else:
                    ago = T("not_checked", lang)

                # service_status_line
                indicator = st.get("indicator") if st else None
                key = f"status_{indicator}" if indicator else "status_unknown"
                service_status_line = T(key, lang)

                # estimated_line
                from src.storage import get_consumption_rate
                cr = get_consumption_rate()
                if cr and b:
                    daily_rate, hours_left, _curr = cr
                    days = int(hours_left // 24)
                    hrs = int(hours_left % 24)
                    if days > 0:
                        remaining = f"{days}d {hrs}h" if lang == "en" else f"{days} 天 {hrs} 小时"
                    elif hrs >= 1:
                        remaining = f"{hrs}h" if lang == "en" else f"{hrs} 小时"
                    else:
                        remaining = "< 1h" if lang == "en" else "不足 1 小时"
                    prefix = "Est." if lang == "en" else "预计可用"
                    estimated_line = f"📊 {prefix} {remaining}"
                else:
                    estimated_line = "📊 --" if lang == "en" else "📊 预计可用 --"

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
