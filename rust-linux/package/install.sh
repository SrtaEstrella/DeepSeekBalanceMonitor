#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "This installer must run as root. Use: sudo ./install.sh" >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BIN_SRC="$SCRIPT_DIR/dsmon"
SERVICE_SRC="$SCRIPT_DIR/dsmon.service"
PLASMOID_SRC="$SCRIPT_DIR/plasmoid"
PLASMOID_DST="/usr/share/plasma/plasmoids/com.github.wenyinos.deepseek-balance-monitor"
ICON_SRC="$PLASMOID_SRC/contents/images/deepseek-balance-monitor.png"
ICON_DST="/usr/share/icons/hicolor/256x256/apps/deepseek-balance-monitor.png"

is_plasma6_session() {
    if [ "${KDE_SESSION_VERSION:-}" = "6" ]; then
        return 0
    fi
    session_user="${SUDO_USER:-$(id -un)}"
    if command -v pgrep >/dev/null 2>&1 && command -v plasmashell >/dev/null 2>&1; then
        if pgrep -u "$session_user" -x plasmashell >/dev/null 2>&1; then
            case "$(plasmashell --version 2>/dev/null)" in
                *" 6."*|*" 7."*) return 0 ;;
            esac
        fi
    fi
    case ":${XDG_CURRENT_DESKTOP:-}:${DESKTOP_SESSION:-}:" in
        *KDE*|*kde*|*Plasma*|*plasma*) ;;
        *) return 1 ;;
    esac
    if command -v plasmashell >/dev/null 2>&1; then
        case "$(plasmashell --version 2>/dev/null)" in
            *" 6."*|*" 7."*) return 0 ;;
        esac
    fi
    return 1
}

should_install_plasmoid() {
    if is_plasma6_session; then
        return 0
    fi
    printf "Plasma 6 desktop session was not detected. Install Plasma widget anyway? [y/N] "
    IFS= read -r answer || answer=""
    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

if [ ! -f "$BIN_SRC" ]; then
    echo "Missing dsmon binary next to install.sh" >&2
    exit 1
fi

INSTALL_PLASMOID=0
if should_install_plasmoid; then
    INSTALL_PLASMOID=1
    if [ ! -f "$PLASMOID_SRC/metadata.json" ]; then
        echo "Missing Plasma widget package next to install.sh" >&2
        exit 1
    fi
    if [ ! -f "$ICON_SRC" ]; then
        echo "Missing Plasma widget icon next to install.sh" >&2
        exit 1
    fi
fi

install -D -m 755 "$BIN_SRC" /usr/local/bin/dsmon
install -D -m 644 "$SERVICE_SRC" /etc/systemd/user/dsmon.service
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    install -D -m 644 "$ICON_SRC" "$ICON_DST"
    install -d -m 755 "$PLASMOID_DST"
    cp -R "$PLASMOID_SRC/." "$PLASMOID_DST/"
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q /usr/share/icons/hicolor || true
    fi
fi

echo "Installed /usr/local/bin/dsmon"
echo "Installed /etc/systemd/user/dsmon.service"
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    echo "Installed Plasma widget: $PLASMOID_DST"
    echo "Installed Plasma widget icon: $ICON_DST"
else
    echo "Skipped Plasma widget installation"
fi
INSTALL_USER="${SUDO_USER:-}"
run_dsmon_for_user() {
    if [ -n "$INSTALL_USER" ] && [ "$INSTALL_USER" != "root" ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$INSTALL_USER" -- /usr/local/bin/dsmon "$@"
    else
        /usr/local/bin/dsmon "$@"
    fi
}
reload_user_systemd() {
    if ! command -v systemctl >/dev/null 2>&1; then
        return
    fi
    if [ -n "$INSTALL_USER" ] && [ "$INSTALL_USER" != "root" ] && command -v runuser >/dev/null 2>&1; then
        install_uid="$(id -u "$INSTALL_USER" 2>/dev/null || true)"
        if [ -n "$install_uid" ] && [ -d "/run/user/$install_uid" ]; then
            echo "Reloading user systemd manager for $INSTALL_USER..."
            runuser -u "$INSTALL_USER" -- env XDG_RUNTIME_DIR="/run/user/$install_uid" systemctl --user daemon-reload || true
            return
        fi
    fi
    echo "Reload user systemd manually if needed:"
    echo "  systemctl --user daemon-reload"
}
prompt_api_key() {
    if [ ! -t 0 ]; then
        echo "Set it with: dsmon set-key <api_key>"
        return
    fi
    printf "Enter DeepSeek API key now (leave blank to skip): "
    HIDE_INPUT=0
    if stty -echo 2>/dev/null; then
        HIDE_INPUT=1
    fi
    IFS= read -r API_KEY || API_KEY=""
    if [ "$HIDE_INPUT" -eq 1 ]; then
        stty echo
    fi
    printf "\n"
    if [ -z "$API_KEY" ]; then
        echo "Skipped API key setup. Set it later with: dsmon set-key <api_key>"
        return
    fi
    if printf "%s\n" "$API_KEY" | run_dsmon_for_user set-key; then
        echo "Running check after saving API key..."
        if ! run_dsmon_for_user check; then
            echo "API key was saved, but the check still failed. Please review the output above."
        fi
    else
        echo "Failed to save API key. Set it later with: dsmon set-key <api_key>" >&2
    fi
}
echo "Running first check..."
CHECK_STATUS=0
CHECK_OUTPUT="$(run_dsmon_for_user check 2>&1)" || CHECK_STATUS=$?
if [ -n "$CHECK_OUTPUT" ]; then
    printf "%s\n" "$CHECK_OUTPUT"
fi
if [ "$CHECK_STATUS" -eq 2 ]; then
    prompt_api_key
elif [ "$CHECK_STATUS" -ne 0 ]; then
    case "$CHECK_OUTPUT" in
        *"Invalid API key"*|*"401 Unauthorized"*) prompt_api_key ;;
        *) echo "First check failed for a non-key reason. Configure the API key later with: dsmon set-key <api_key>" ;;
    esac
fi
reload_user_systemd
echo "Run dsmon as your normal user; root is only needed for this installer."
echo "Enable daemon for the current user:"
echo "  systemctl --user enable --now dsmon.service"
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    echo "Add widget: right-click panel/desktop -> Add Widgets -> DeepSeek Balance Monitor"
    echo "If the old Plasma widget UI or icon is still shown, restart plasmashell or log out and log back in."
fi
