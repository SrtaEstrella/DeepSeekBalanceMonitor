import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.plasmoid

PlasmoidItem {
    id: root

    property bool configured: false
    property bool ok: false
    property bool checking: false
    property bool lowBalance: false
    property string errorText: ""
    property string configPath: ""
    property string totalCurrency: "CNY"
    property string totalBalance: "--"
    property string lastCheck: "Not checked"
    property int intervalMinutes: 10
    property real thresholdYuan: 1.0
    property var balances: ({})
    property string language: systemLanguage()
    property bool daemonChecked: false
    property bool daemonRunning: true
    property string pendingDaemonAction: ""
    property string serviceStatus: "unknown"
    property bool serviceDegraded: false
    property bool serviceStatusChecked: false
    property bool apiAlertEnabled: true
    property string iconTheme: "default"
    property var iconColors: ({})
    property bool iconStroke: false
    property var consumptionRate: null
    readonly property string notificationIconPath: "/usr/share/icons/hicolor/256x256/apps/deepseek-balance-monitor.png"
    readonly property color warmGray: "#8a8078"
    readonly property color glassTextColor: "#ffffff"
    readonly property int balanceTextPointSize: 15

    Plasmoid.icon: !ok || !daemonRunning ? "dialog-warning" : "deepseek-balance-monitor"
    Plasmoid.title: tr("title")
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    toolTipMainText: tooltipText
    preferredRepresentation: desktopWidget ? fullRepresentation : compactRepresentation

    readonly property bool desktopWidget: Plasmoid.formFactor === PlasmaCore.Types.Planar
    readonly property string compactLabel: daemonChecked && !daemonRunning ? "!" : (ok ? totalBalance : (checking ? "..." : "!"))
    readonly property string tooltipText: checking
        ? tr("checking")
        : (daemonChecked && !daemonRunning
            ? tr("error") + ": " + tr("daemonStopped")
            : (ok
                ? tr("totalBalance") + ": " + totalBalance + " " + totalCurrency
                : tr("error") + ": " + (configured ? (errorText || tr("balanceEmpty")) : tr("noKey"))))
    readonly property string balanceStatusLine: ok
        ? tr("totalBalance") + ": " + totalBalance + " " + totalCurrency
        : (configured ? errorText : tr("noKey"))
    readonly property string serviceStatusLine: tr("serviceStatus") + serviceStatusText()
    readonly property string statusLine: daemonChecked && !daemonRunning ? tr("daemonStopped") : (serviceDegraded ? serviceStatusLine : balanceStatusLine)
    readonly property color statusColor: !configured || !ok || lowBalance || !daemonRunning
        ? Kirigami.Theme.negativeTextColor
        : (serviceDegraded ? warmGray : Kirigami.Theme.positiveTextColor)
    readonly property string balanceNumberColor: iconFill
    readonly property string iconFill: checking ? iconColor("nodata") : (daemonChecked && !daemonRunning ? iconColor("low") : (ok ? (lowBalance ? iconColor("low") : (serviceDegraded ? iconColor("degraded") : iconColor("ok"))) : iconColor(configured ? "low" : "nodata")))
    readonly property color iconTextColor: textColor(iconFill)

    function runCommand(command) {
        executable.connectSource(command)
    }

    function themePalette(theme) {
        var palettes = {
            "default": { ok: "#3c6966", low: "#b9463c", degraded: "#78695a", nodata: "#69696e" },
            "contrast": { ok: "#2d8074", low: "#d4342e", degraded: "#8b6914", nodata: "#555555" },
            "bright": { ok: "#c8ebe6", low: "#f5d2cd", degraded: "#ebdccd", nodata: "#d7d7dc" },
            "dark_mode": { ok: "#509b94", low: "#d7645a", degraded: "#9b8c73", nodata: "#7d7d82" },
            "mono": { ok: "#555555", low: "#222222", degraded: "#777777", nodata: "#999999" }
        }
        return palettes[theme] || palettes["default"]
    }

    function customColor(key) {
        var value = iconColors && iconColors[key] ? String(iconColors[key]) : ""
        return /^[0-9a-fA-F]{6}$/.test(value) ? "#" + value : ""
    }

    function iconColor(key) {
        if (iconTheme === "custom") {
            var custom = customColor(key)
            if (custom.length > 0) {
                return custom
            }
        }
        return themePalette(iconTheme)[key]
    }

    function textColor(hex) {
        var value = String(hex).replace("#", "")
        var r = parseInt(value.substring(0, 2), 16)
        var g = parseInt(value.substring(2, 4), 16)
        var b = parseInt(value.substring(4, 6), 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) > 170 ? "#000000" : "#ffffff"
    }

    function htmlEscape(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
    }

    function coloredNumber(value) {
        var text = String(value)
        if (!/^-?\d+(\.\d+)?$/.test(text)) {
            return htmlEscape(text)
        }
        return "<span style=\"color:" + balanceNumberColor + "\">" + htmlEscape(text) + "</span>"
    }

    function systemLanguage() {
        var localeName = Qt.locale().name
        if (!localeName || String(localeName).length === 0) {
            return "zh"
        }
        return String(localeName).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = {
            title: "DeepSeek 余额监控",
            checking: "查询中...",
            error: "错误",
            totalBalance: "总余额",
            noKey: "未配置 DeepSeek API Key。",
            noOutput: "dsmon 没有输出。",
            parseFailed: "解析 dsmon 输出失败：",
            check: "查询",
            queryInterval: "查询间隔",
            minutes: "分钟",
            balanceThreshold: "余额预警线",
            lastCheck: "上次查询",
            balances: "余额明细",
            toppedUp: "充值",
            granted: "赠送",
            balTitle: "DeepSeek 余额：",
            queryError: "查询出错",
            notChecked: "尚未查询",
            serviceStatus: "DeepSeek API 服务状态：",
            rainmeterServiceLabel: "API 服务状态",
            serviceNormal: "服务正常",
            statusMinor: "轻微异常",
            statusMajor: "严重异常",
            statusCritical: "关键不可用",
            statusMaintenance: "维护中",
            statusUnknown: "服务状态未知",
            apiDegradedTitle: "⚠ DeepSeek API 服务异常",
            apiDegradedMsg: "检测到 API 服务状态异常：",
            apiRecoveredTitle: "✅ DeepSeek API 服务恢复",
            apiRecoveredMsg: "API 服务已恢复正常。",
            viewBalance: "查看余额",
            checkNow: "立即查询",
            topUp: "充值",
            startDaemon: "启动守护进程",
            stopDaemon: "退出守护进程",
            daemonStartFailed: "dsmon 守护进程启动失败",
            daemonStopFailed: "dsmon 守护进程退出失败",
            daemonNoConsoleError: "没有控制台错误输出。",
            balanceEmpty: "暂无余额数据，请等待或手动查询。",
            balanceErrorTitle: "余额查询失败",
            daemonStopped: "dsmon 后台进程未运行，请启动 dsmon.service。",
            dailyRate: "日均消耗",
            estimated: "预计可用",
            fallbackBalanceLine: "⚠ 请打开原进程",
            fallbackLastCheck: "尚未查询",
            fallbackServiceStatusLine: "⚪ 未连接",
            fallbackEstimatedLine: "📊 等待数据"
        }
        var en = {
            title: "DeepSeek Balance Monitor",
            checking: "Checking...",
            error: "Error",
            totalBalance: "Total balance",
            noKey: "DeepSeek API key is not configured.",
            noOutput: "No output from dsmon.",
            parseFailed: "Failed to parse dsmon output: ",
            check: "Check",
            queryInterval: "Query interval",
            minutes: "minutes",
            balanceThreshold: "Balance threshold",
            lastCheck: "Last check",
            balances: "Balances",
            toppedUp: "topped up",
            granted: "granted",
            balTitle: "DeepSeek Balance:",
            queryError: "Query error",
            notChecked: "Not checked",
            serviceStatus: "DeepSeek API Status:",
            rainmeterServiceLabel: "API Status",
            serviceNormal: "All Systems Operational",
            statusMinor: "Minor Outage",
            statusMajor: "Major Outage",
            statusCritical: "Critical Outage",
            statusMaintenance: "Under Maintenance",
            statusUnknown: "Status Unknown",
            apiDegradedTitle: "⚠ DeepSeek API Degraded",
            apiDegradedMsg: "API service status has changed: ",
            apiRecoveredTitle: "✅ DeepSeek API Recovered",
            apiRecoveredMsg: "API service is back to normal.",
            viewBalance: "View Balance",
            checkNow: "Check Now",
            topUp: "Top Up",
            startDaemon: "Start daemon",
            stopDaemon: "Stop daemon",
            daemonStartFailed: "Failed to start dsmon daemon",
            daemonStopFailed: "Failed to stop dsmon daemon",
            daemonNoConsoleError: "No console error output.",
            balanceEmpty: "No balance data yet. Please wait or check now.",
            balanceErrorTitle: "Balance check failed",
            daemonStopped: "dsmon background process is not running. Start dsmon.service.",
            dailyRate: "Avg",
            estimated: "Est.",
            fallbackBalanceLine: "⚠ Open the main app",
            fallbackLastCheck: "Not checked",
            fallbackServiceStatusLine: "⚪ Not Connected",
            fallbackEstimatedLine: "📊 Waiting for data"
        }
        var table = language === "zh" ? zh : en
        return table[key] || key
    }

    function refresh() {
        checking = true
        runCommand("systemctl --user is-active dsmon.service")
        runCommand("/usr/local/bin/dsmon widget-status")
    }

    function toggleDaemon() {
        pendingDaemonAction = daemonChecked && !daemonRunning ? "start" : "stop"
        runCommand("systemctl --user " + pendingDaemonAction + " dsmon.service")
    }

    function openTopUp() {
        runCommand("/usr/bin/xdg-open " + shellQuote("https://platform.deepseek.com/top_up"))
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function exitCode(data) {
        var code = data["exit code"]
        if (code === undefined) {
            code = data["exitCode"]
        }
        if (code === undefined) {
            code = data["exit_code"]
        }
        return code === undefined || code === "" ? 0 : Number(code)
    }

    function commandFailed(data, stderr) {
        return exitCode(data) !== 0 || stderr.trim().length > 0
    }

    function consoleMessage(stdout, stderr) {
        var text = stderr.trim().length > 0 ? stderr.trim() : stdout.trim()
        return text.length > 0 ? text : tr("daemonNoConsoleError")
    }

    function notifyDaemonError(action, stdout, stderr) {
        var title = action === "start" ? tr("daemonStartFailed") : tr("daemonStopFailed")
        runCommand("/usr/bin/notify-send --app-name " + shellQuote(tr("title"))
            + " --icon " + shellQuote(notificationIconPath)
            + " " + shellQuote(title)
            + " " + shellQuote(consoleMessage(stdout, stderr)))
    }

    function notifyApiStatusChange(degraded) {
        var title = degraded ? tr("apiDegradedTitle") : tr("apiRecoveredTitle")
        var message = (degraded ? tr("apiDegradedMsg") : tr("apiRecoveredMsg") + " ") + serviceStatusMarkup()
        runCommand("/usr/bin/notify-send --app-name " + shellQuote(tr("title"))
            + " --icon " + shellQuote(notificationIconPath)
            + " " + shellQuote(title)
            + " " + shellQuote(message))
    }

    function verifyDaemonAction(stdout, stderr) {
        if (pendingDaemonAction === "start" && stdout.trim() !== "active") {
            notifyDaemonError(pendingDaemonAction, stdout, stderr)
        } else if (pendingDaemonAction === "stop" && stdout.trim() === "active") {
            notifyDaemonError(pendingDaemonAction, stdout, stderr)
        }
        pendingDaemonAction = ""
    }

    function serviceStatusText() {
        switch (serviceStatus) {
        case "none":
            return tr("serviceNormal")
        case "minor":
            return tr("statusMinor")
        case "major":
            return tr("statusMajor")
        case "critical":
            return tr("statusCritical")
        case "maintenance":
            return tr("statusMaintenance")
        default:
            return tr("statusUnknown")
        }
    }

    function serviceStatusMarkup() {
        return serviceStatusEmoji() + " " + htmlEscape(serviceStatusText())
    }

    function serviceStatusEmoji() {
        switch (serviceStatus) {
        case "none":
            return "🟢"
        case "minor":
        case "maintenance":
            return "🟡"
        case "major":
            return "🟠"
        case "critical":
            return "🔴"
        default:
            return "⚪"
        }
    }

    function relativeLastCheck() {
        if (!lastCheck || lastCheck === "Not checked" || lastCheck === tr("notChecked")) {
            return tr("notChecked")
        }
        var parsed = Date.parse(lastCheck.replace(" ", "T"))
        if (isNaN(parsed)) {
            return lastCheck
        }
        var seconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000))
        if (seconds < 60) {
            return language === "zh" ? "刚刚" : "just now"
        }
        var value = seconds < 3600 ? Math.floor(seconds / 60)
            : seconds < 86400 ? Math.floor(seconds / 3600)
            : Math.floor(seconds / 86400)
        if (language === "zh") {
            return value + " " + (seconds < 3600 ? "分钟" : seconds < 86400 ? "小时" : "天") + "前"
        }
        return value + " " + (seconds < 3600 ? "minutes" : seconds < 86400 ? "hours" : "days") + " ago"
    }

    function labelSeparator() {
        return language === "zh" ? "：" : ": "
    }

    function applyServiceStatus(status, degraded) {
        var changed = serviceStatusChecked && serviceStatus !== status
        serviceStatus = status
        serviceDegraded = degraded
        if (changed && apiAlertEnabled) {
            notifyApiStatusChange(degraded)
        }
        serviceStatusChecked = true
    }

    function notificationTitle() {
        return tr("balTitle")
    }

    function estimatedAvailabilityText() {
        if (!consumptionRate) {
            return tr("estimated") + " --"
        }
        var hoursLeft = Number(consumptionRate.hours_left)
        if (!isFinite(hoursLeft) || hoursLeft < 0) {
            return tr("estimated") + " --"
        }
        var daysLeft = Math.floor(hoursLeft / 24)
        var hoursRemainder = Math.floor(hoursLeft % 24)
        return language === "zh"
            ? tr("estimated") + " " + daysLeft + " 天 " + hoursRemainder + " 小时"
            : tr("estimated") + " " + daysLeft + "d " + hoursRemainder + "h remaining"
    }

    function rainmeterBalanceLine() {
        if (daemonChecked && !daemonRunning) {
            return tr("fallbackBalanceLine")
        }
        if (ok) {
            return "💰 " + totalBalance + " " + totalCurrency
        }
        return "💰 -- CNY"
    }

    function rainmeterLastValue() {
        return daemonChecked && !daemonRunning ? tr("fallbackLastCheck") : relativeLastCheck()
    }

    function rainmeterServiceValue() {
        return daemonChecked && !daemonRunning ? tr("fallbackServiceStatusLine") : serviceStatusMarkup()
    }

    function rainmeterEstimatedLine() {
        return daemonChecked && !daemonRunning ? tr("fallbackEstimatedLine") : "📊 " + estimatedAvailabilityText()
    }

    function balanceMessage() {
        var keys = Object.keys(balances)
        var lines = []
        if (ok && keys.length > 0) {
            var code = balances[totalCurrency] ? totalCurrency : keys[0]
            var item = balances[code]
            lines.push("💰 " + Number(item.total_balance).toFixed(2) + " " + code
                + (language === "zh" ? "（充值 " : " (Topped ")
                + Number(item.topped_up_balance).toFixed(2)
                + (language === "zh" ? "，赠送 " : ", Granted ")
                + Number(item.granted_balance).toFixed(2)
                + (language === "zh" ? "）" : ")"))
            if (consumptionRate) {
                lines.push("📊 " + (language === "zh"
                    ? tr("dailyRate") + " " + Number(consumptionRate.daily_rate).toFixed(2) + " " + consumptionRate.currency + " | " + estimatedAvailabilityText()
                    : tr("dailyRate") + ": " + Number(consumptionRate.daily_rate).toFixed(2) + " " + consumptionRate.currency + "/day | " + estimatedAvailabilityText()))
            }
        }
        lines.push("📡 " + tr("serviceStatus") + serviceStatusEmoji() + " " + serviceStatusText())
        if (!configured) {
            lines.push("🕐 " + tr("queryError") + labelSeparator() + tr("noKey"))
        } else if (!ok || (daemonChecked && !daemonRunning)) {
            lines.push("🕐 " + tr("queryError") + labelSeparator()
                + (daemonChecked && !daemonRunning ? tr("daemonStopped") : (errorText || tr("noOutput"))))
        } else if (lastCheck && lastCheck.length > 0) {
            lines.push("🕐 " + tr("lastCheck") + labelSeparator() + relativeLastCheck())
        } else {
            lines.push("🕐 " + tr("notChecked"))
        }
        return lines.join("\n")
    }

    function showBalanceNotification() {
        runCommand("/usr/bin/notify-send --app-name " + shellQuote(tr("title"))
            + " --icon " + shellQuote(notificationIconPath)
            + " " + shellQuote(notificationTitle())
            + " " + shellQuote(balanceMessage()))
    }

    function updateAttentionStatus() {
        Plasmoid.status = !ok || lowBalance || serviceDegraded || (daemonChecked && !daemonRunning)
            ? PlasmaCore.Types.NeedsAttentionStatus
            : PlasmaCore.Types.ActiveStatus
    }

    function applyStatus(stdout, stderr) {
        checking = false
        if (!stdout || stdout.trim().length === 0) {
            ok = false
            errorText = stderr && stderr.length > 0 ? stderr.trim() : tr("noOutput")
            return
        }
        try {
            var status = JSON.parse(stdout)
            configured = !!status.configured
            configPath = status.config_path || ""
            intervalMinutes = status.interval_minutes || 10
            thresholdYuan = status.threshold_yuan || 1.0
            apiAlertEnabled = status.api_alert_enabled === undefined ? true : !!status.api_alert_enabled
            iconTheme = status.theme || "default"
            iconColors = status.icon_colors || ({})
            iconStroke = !!status.icon_stroke
            consumptionRate = status.consumption_rate || null
            var nextServiceStatus = status.service_status || "unknown"
            applyServiceStatus(nextServiceStatus,
                status.service_degraded === undefined ? nextServiceStatus !== "none" : !!status.service_degraded)
            language = status.ui_language === "zh" || status.ui_language === "en" ? status.ui_language : systemLanguage()
            if (configured && !status.ok && serviceDegraded && Object.keys(balances).length > 0) {
                ok = true
                errorText = ""
                updateAttentionStatus()
                return
            }
            ok = !!status.ok
            lowBalance = !!status.low_balance
            errorText = status.error || ""
            lastCheck = status.last_check || "Not checked"
            totalCurrency = status.total_currency || "CNY"
            totalBalance = status.total_balance === null || status.total_balance === undefined
                ? "--"
                : Number(status.total_balance).toFixed(2)
            balances = status.balances || ({})
            updateAttentionStatus()
        } catch (error) {
            ok = false
            errorText = tr("parseFailed") + error
            updateAttentionStatus()
        }
    }

    Timer {
        interval: Math.max(1, intervalMinutes) * 60 * 1000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: refresh()
    }

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var stdout = data["stdout"] || ""
            var stderr = data["stderr"] || ""
            if (String(sourceName).indexOf("widget-status") !== -1) {
                root.applyStatus(stdout, stderr)
            } else if (String(sourceName).indexOf("is-active dsmon.service") !== -1) {
                root.daemonChecked = true
                root.daemonRunning = stdout.trim() === "active"
                if (root.pendingDaemonAction.length > 0) {
                    root.verifyDaemonAction(stdout, stderr)
                }
                root.updateAttentionStatus()
            } else if (String(sourceName).indexOf("start dsmon.service") !== -1 || String(sourceName).indexOf("stop dsmon.service") !== -1) {
                if (root.commandFailed(data, stderr)) {
                    root.notifyDaemonError(root.pendingDaemonAction, stdout, stderr)
                    root.pendingDaemonAction = ""
                } else {
                    runCommand("systemctl --user is-active dsmon.service")
                }
            }
            disconnectSource(sourceName)
        }
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: tr("viewBalance")
            icon.name: "view-visible"
            onTriggered: root.showBalanceNotification()
        },
        PlasmaCore.Action {
            text: tr("checkNow")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        },
        PlasmaCore.Action {
            text: tr("topUp")
            icon.name: "deepseek-balance-monitor"
            onTriggered: root.openTopUp()
        },
        PlasmaCore.Action {
            isSeparator: true
        },
        PlasmaCore.Action {
            text: daemonChecked && !daemonRunning ? tr("startDaemon") : tr("stopDaemon")
            icon.name: daemonChecked && !daemonRunning ? "media-playback-start" : "application-exit"
            onTriggered: root.toggleDaemon()
        }
    ]

    compactRepresentation: MouseArea {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 2
        Layout.minimumHeight: Kirigami.Units.gridUnit * 2
        Layout.preferredWidth: Kirigami.Units.gridUnit * 2.2
        Layout.preferredHeight: Kirigami.Units.gridUnit * 2.2
        acceptedButtons: Qt.LeftButton
        onClicked: root.showBalanceNotification()

        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width, parent.height) * 0.86
            height: width
            radius: width * 0.18
            color: root.iconFill
            border.width: root.iconStroke ? Math.max(1, width * 0.08) : 0
            border.color: root.iconTextColor

            PlasmaComponents.Label {
                anchors.centerIn: parent
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: root.compactLabel
                color: root.iconTextColor
                font.bold: true
                font.pixelSize: Math.max(10, parent.width * (text.length <= 2 ? 0.42 : 0.32))
                elide: Text.ElideRight
            }
        }
    }

    fullRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 15
        Layout.maximumWidth: Kirigami.Units.gridUnit * 18
        Layout.minimumHeight: contentColumn.implicitHeight + Kirigami.Units.largeSpacing * 1.3
        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredHeight: contentColumn.implicitHeight + Kirigami.Units.largeSpacing * 1.3
        Layout.maximumHeight: contentColumn.implicitHeight + Kirigami.Units.largeSpacing * 1.3

        Rectangle {
            id: glassCard
            anchors.fill: parent
            radius: Kirigami.Units.gridUnit
            color: "transparent"
            clip: true
            border.color: Qt.rgba(1, 1, 1, root.desktopWidget ? 0.42 : 0.28)
            border.width: 1

            Rectangle {
                width: parent.width * 0.66
                height: width
                x: -width * 0.22
                y: -height * 0.28
                radius: width / 2
                color: root.iconFill
                opacity: root.desktopWidget ? 0.16 : 0.10
            }

            Rectangle {
                width: parent.width * 0.48
                height: width
                x: parent.width - width * 0.62
                y: parent.height - height * 0.46
                radius: width / 2
                color: Kirigami.Theme.highlightColor
                opacity: root.desktopWidget ? 0.12 : 0.08
            }

            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, root.desktopWidget ? 0.18 : 0.12) }
                    GradientStop { position: 0.45; color: Qt.rgba(0, 0, 0, root.desktopWidget ? 0.16 : 0.18) }
                    GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, root.desktopWidget ? 0.28 : 0.24) }
                }
            }

            Rectangle {
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: Kirigami.Units.largeSpacing
                }
                height: 1
                radius: 1
                color: Qt.rgba(1, 1, 1, 0.42)
            }
        }

        ColumnLayout {
            id: contentColumn
            anchors {
                left: glassCard.left
                right: glassCard.right
                top: glassCard.top
                margins: Kirigami.Units.largeSpacing * 0.65
            }
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Rectangle {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 2.6
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 2.6
                    radius: width / 2
                    color: root.iconFill
                    border.color: root.iconTextColor
                    border.width: root.iconStroke ? 2 : 0

                    Image {
                        anchors.centerIn: parent
                        width: parent.width * 0.72
                        height: width
                        source: "../images/deepseek-balance-monitor.png"
                        fillMode: Image.PreserveAspectFit
                    }
                }

                PlasmaExtras.ShadowedLabel {
                    Layout.fillWidth: true
                    text: root.rainmeterBalanceLine()
                    color: root.glassTextColor
                    font.bold: true
                    font.pointSize: root.balanceTextPointSize
                    elide: Text.ElideRight
                }
                PlasmaComponents.Button {
                    id: refreshButton
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 3.8
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 1.9
                    text: tr("check")
                    icon.name: "view-refresh"
                    enabled: !root.checking
                    onClicked: root.refresh()
                    background: Rectangle {
                        radius: height / 2
                        color: refreshButton.pressed ? Qt.rgba(1, 1, 1, 0.26) : Qt.rgba(1, 1, 1, 0.14)
                        border.color: Qt.rgba(1, 1, 1, 0.46)
                        border.width: 1
                    }
                    contentItem: PlasmaExtras.ShadowedLabel {
                        text: refreshButton.text
                        color: root.glassTextColor
                        font.bold: true
                        font.pointSize: 10
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            PlasmaExtras.ShadowedLabel {
                Layout.fillWidth: true
                visible: false
                text: ""
                color: root.glassTextColor
                font.pointSize: 11
                Layout.preferredHeight: 0
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Kirigami.Units.smallSpacing
                columnSpacing: Kirigami.Units.largeSpacing

                PlasmaExtras.ShadowedLabel {
                    text: "🕐 " + tr("lastCheck") + root.labelSeparator()
                    color: root.glassTextColor
                    font.pointSize: 10
                }
                PlasmaExtras.ShadowedLabel {
                    Layout.fillWidth: true
                    text: root.rainmeterLastValue()
                    color: root.glassTextColor
                    font.pointSize: 10
                    elide: Text.ElideRight
                }
                PlasmaExtras.ShadowedLabel {
                    text: "📡 " + tr("rainmeterServiceLabel") + root.labelSeparator()
                    color: root.glassTextColor
                    font.pointSize: 10
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaExtras.ShadowedLabel {
                        Layout.fillWidth: true
                        text: root.rainmeterServiceValue()
                        color: root.glassTextColor
                        font.pointSize: 10
                        elide: Text.ElideRight
                    }
                }
            }

            PlasmaExtras.ShadowedLabel {
                Layout.fillWidth: true
                text: root.rainmeterEstimatedLine()
                color: root.glassTextColor
                font.bold: true
                font.pointSize: root.balanceTextPointSize
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
        }
    }
}
