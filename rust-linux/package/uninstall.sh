#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "This uninstaller must run as root. Use: sudo ./uninstall.sh" >&2
    exit 1
fi

SERVICE_NAME="dsmon.service"
BIN_DST="/usr/local/bin/dsmon"
SERVICE_DST="/etc/systemd/user/$SERVICE_NAME"
PLASMOID_DST="/usr/share/plasma/plasmoids/com.github.wenyinos.deepseek-balance-monitor"
ICON_DST="/usr/share/icons/hicolor/256x256/apps/deepseek-balance-monitor.png"

CORE_INSTALLED=0
if [ -e "$BIN_DST" ] || [ -e "$SERVICE_DST" ]; then
    CORE_INSTALLED=1
fi

PLASMA_FILES_FOUND=0
if [ -d "$PLASMOID_DST" ] || [ -f "$ICON_DST" ]; then
    PLASMA_FILES_FOUND=1
fi

if [ "$CORE_INSTALLED" -eq 0 ]; then
    echo "dsmon executable and systemd service were not found. Core app is not installed."
    if [ "$PLASMA_FILES_FOUND" -eq 0 ]; then
        echo "Nothing to uninstall."
        exit 0
    fi
fi

run_user_systemctl() {
    service_user="$1"
    shift
    service_uid="$(id -u "$service_user" 2>/dev/null || true)"
    if [ -z "$service_uid" ] || [ ! -d "/run/user/$service_uid" ]; then
        echo "Skipping user systemd action for $service_user; no active user session was found."
        return
    fi
    if command -v runuser >/dev/null 2>&1; then
        runuser -u "$service_user" -- env XDG_RUNTIME_DIR="/run/user/$service_uid" systemctl --user "$@" || true
    else
        echo "runuser is not available. Run manually as $service_user: systemctl --user $*"
    fi
}

INSTALL_USER="${SUDO_USER:-}"
if [ "$CORE_INSTALLED" -eq 1 ]; then
    if [ -n "$INSTALL_USER" ] && [ "$INSTALL_USER" != "root" ]; then
        echo "Stopping and disabling $SERVICE_NAME for user $INSTALL_USER..."
        run_user_systemctl "$INSTALL_USER" disable --now "$SERVICE_NAME"
    else
        echo "No non-root sudo user detected. If the service is running, stop it as your normal user:"
        echo "  systemctl --user disable --now $SERVICE_NAME"
    fi
fi

if [ "$CORE_INSTALLED" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    systemctl --global disable "$SERVICE_NAME" >/dev/null 2>&1 || true
fi
if [ -e "$SERVICE_DST" ]; then
    rm -f "$SERVICE_DST"
    echo "Removed $SERVICE_DST"
else
    echo "Not found: $SERVICE_DST"
fi
if [ -e "$BIN_DST" ]; then
    rm -f "$BIN_DST"
    echo "Removed $BIN_DST"
else
    echo "Not found: $BIN_DST"
fi

if [ "$CORE_INSTALLED" -eq 1 ] && [ -n "$INSTALL_USER" ] && [ "$INSTALL_USER" != "root" ]; then
    run_user_systemctl "$INSTALL_USER" daemon-reload
fi

echo "User data and configuration were not removed."

if [ "$PLASMA_FILES_FOUND" -eq 1 ]; then
    echo ""
    echo "Plasma widget files were detected and left in place intentionally."
    echo "Do not delete the widget directory while the widget is still on your panel or desktop."
    echo "To remove it safely:"
    echo "  1. In Plasma, remove every DeepSeek Balance Monitor widget from panels/desktops."
    echo "  2. Log out and log back in, or restart plasmashell."
    echo "  3. After no widget instance is active, remove the package files manually:"
    echo "     sudo rm -rf $PLASMOID_DST"
    echo "     sudo rm -f $ICON_DST"
    echo "     sudo gtk-update-icon-cache -q /usr/share/icons/hicolor"
else
    echo "No Plasma widget package files were detected."
fi
