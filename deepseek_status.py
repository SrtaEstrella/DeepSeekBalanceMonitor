#!/usr/bin/env python3
"""
DeepSeek Service Status — API version
使用 Statuspage REST API 获取 DeepSeek 服务状态，无需刮 HTML。

状态 endpoint:      https://status.deepseek.com/api/v2/status.json
组件 endpoint:      https://status.deepseek.com/api/v2/components.json
事件 endpoint:      https://status.deepseek.com/api/v2/incidents.json

status.indicator 的可能值（整体状态）:
  "none"        全部正常 (All Systems Operational)
  "minor"       部分服务轻微异常 (Minor Outage)
  "major"       部分服务严重异常 (Major Outage)
  "critical"    关键服务不可用 (Critical Outage)
  "maintenance" 维护中 (Under Maintenance)

components[].status 的可能值（服务级状态）:
  "operational"          正常运行
  "degraded_performance" 性能下降
  "partial_outage"       部分不可用
  "major_outage"         严重故障
  "under_maintenance"    维护中

用法:
  python deepseek_status.py           单次检查
  python deepseek_status.py --json    JSON 输出
  python deepseek_status.py --watch N 每 N 秒持续监控
"""

import urllib.request
import json
import time
import sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
BASE = "https://status.deepseek.com/api/v2"
UA  = "DeepSeekStatusMonitor/1.0"

STATUS_LABEL = {
    "operational":          "正常运行",
    "degraded_performance": "性能下降",
    "partial_outage":       "部分不可用",
    "major_outage":         "严重故障",
    "under_maintenance":    "维护中",
}

STATUS_ICON = {
    "operational":          "\U0001f7e2",  # 🟢
    "degraded_performance": "\U0001f7e1",  # 🟡
    "partial_outage":       "\U0001f7e0",  # 🟠
    "major_outage":         "\U0001f534",  # 🔴
    "under_maintenance":    "\U0001f535",  # 🔵
}

INDICATOR_ICON = {
    "none":        "\u2705",
    "minor":       "\U0001f7e1",
    "major":       "\U0001f7e0",
    "critical":    "\U0001f534",
    "maintenance": "\U0001f535",
}

INDICATOR_LABEL = {
    "none":        "All Systems Operational",
    "minor":       "Minor Outage",
    "major":       "Major Outage",
    "critical":    "Critical Outage",
    "maintenance": "Under Maintenance",
}

def get_json(path):
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return None

def fetch_status():
    status = get_json("status.json")
    components = get_json("components.json")
    return status, components

def main():
    import argparse
    p = argparse.ArgumentParser(description="DeepSeek Status (API)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--watch", type=int, metavar="SEC")
    args = p.parse_args()

    def check():
        s, c = fetch_status()
        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")
        if not s:
            return {"error": "Failed to fetch status", "timestamp": now}
        si = s.get("status", {})
        return {
            "timestamp": now,
            "indicator": si.get("indicator"),
            "description": si.get("description"),
            "components": [
                {"name": x["name"], "status": x["status"]}
                for x in (c or {}).get("components", [])
            ] if c else [],
        }

    if args.watch:
        print(f"Monitoring DeepSeek status every {args.watch}s ...", flush=True)
        try:
            while True:
                data = check()
                if args.json:
                    print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
                else:
                    print(format_text(data), flush=True)
                nxt = (datetime.now(CST) + timedelta(seconds=args.watch))
                print(f"\nNext: {nxt.strftime('%H:%M:%S CST')}\n", flush=True)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)
    else:
        data = check()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(format_text(data))


def format_text(data):
    L = []
    L.append("=" * 56)
    L.append(f"  DeepSeek Status  ({data.get('timestamp', '')})")
    L.append("=" * 56)
    if "error" in data:
        L.append(f"\n  Error: {data['error']}")
        return "\n".join(L)

    ind = data.get("indicator", "")
    icon = INDICATOR_ICON.get(ind, "\u26aa")
    label = INDICATOR_LABEL.get(ind, ind)
    L.append(f"\n  Overall: {icon} {label}")

    for comp in data.get("components", []):
        st = comp["status"]
        ci = STATUS_ICON.get(st, "\u26aa")
        cl = STATUS_LABEL.get(st, st)
        L.append(f"  {ci} {comp['name']}  — {cl}")

    L.append("\n" + "=" * 56)
    return "\n".join(L)


if __name__ == "__main__":
    main()
