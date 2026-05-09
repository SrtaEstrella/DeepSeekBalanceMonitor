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
fi

install -D -m 755 "$BIN_SRC" /usr/local/bin/dsmon
install -D -m 644 "$SERVICE_SRC" /etc/systemd/user/dsmon.service
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    install -d -m 755 "$PLASMOID_DST"
    cp -R "$PLASMOID_SRC/." "$PLASMOID_DST/"
fi

echo "Installed /usr/local/bin/dsmon"
echo "Installed /etc/systemd/user/dsmon.service"
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    echo "Installed Plasma widget: $PLASMOID_DST"
else
    echo "Skipped Plasma widget installation"
fi
echo "Create config: dsmon init-config"
echo "Run dsmon as your normal user; root is only needed for this installer."
echo "Enable daemon for the current user:"
echo "  systemctl --user daemon-reload"
echo "  systemctl --user enable --now dsmon.service"
if [ "$INSTALL_PLASMOID" -eq 1 ]; then
    echo "Add widget: right-click panel/desktop -> Add Widgets -> DeepSeek Balance Monitor"
    echo "After installing or upgrading the Plasma widget, log out and log back in if the old widget UI is still shown."
fi
