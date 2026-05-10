import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.core as PlasmaCore
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
    readonly property string notificationIconPath: "/usr/share/icons/hicolor/256x256/apps/deepseek-balance-monitor.png"
    readonly property color warmGray: "#8a8078"

    Plasmoid.icon: !ok || !daemonRunning ? "dialog-warning" : "deepseek-balance-monitor"
    Plasmoid.title: tr("title")
    toolTipMainText: tooltipText
    preferredRepresentation: compactRepresentation

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

    function runCommand(command) {
        executable.connectSource(command)
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
            serviceNormal: "🟢 服务正常",
            statusMinor: "🟡 轻微异常",
            statusMajor: "🟠 严重异常",
            statusCritical: "🔴 关键不可用",
            statusMaintenance: "🔧 维护中",
            statusUnknown: "⚪ 服务状态未知",
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
            daemonStopped: "dsmon 后台进程未运行，请启动 dsmon.service。"
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
            serviceNormal: "🟢 All Systems Operational",
            statusMinor: "🟡 Minor Outage",
            statusMajor: "🟠 Major Outage",
            statusCritical: "🔴 Critical Outage",
            statusMaintenance: "🔧 Under Maintenance",
            statusUnknown: "⚪ Status Unknown",
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
            daemonStopped: "dsmon background process is not running. Start dsmon.service."
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
        var message = degraded ? tr("apiDegradedMsg") + serviceStatusText() : tr("apiRecoveredMsg")
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

    function balanceMessage() {
        var keys = Object.keys(balances)
        var lines = []
        if (ok && keys.length > 0) {
            var code = balances[totalCurrency] ? totalCurrency : keys[0]
            var item = balances[code]
            lines.push(Number(item.total_balance).toFixed(2) + " " + code
                + (language === "zh" ? "（充值 " : " (Topped ")
                + Number(item.topped_up_balance).toFixed(2)
                + (language === "zh" ? "，赠送 " : ", Granted ")
                + Number(item.granted_balance).toFixed(2)
                + (language === "zh" ? "）" : ")"))
        }
        if (!configured) {
            lines.push(tr("queryError") + ": " + tr("noKey"))
        } else if (!ok || (daemonChecked && !daemonRunning)) {
            lines.push(tr("queryError") + ": "
                + (daemonChecked && !daemonRunning ? tr("daemonStopped") : (errorText || tr("noOutput"))))
        } else if (lastCheck && lastCheck.length > 0) {
            lines.push(tr("lastCheck") + ": " + lastCheck)
        } else {
            lines.push(tr("notChecked"))
        }
        lines.push(serviceStatusLine)
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
            color: root.checking
                ? Kirigami.Theme.disabledTextColor
                : root.statusColor

            PlasmaComponents.Label {
                anchors.centerIn: parent
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: root.compactLabel
                color: "white"
                font.bold: true
                font.pixelSize: Math.max(10, parent.width * (text.length <= 2 ? 0.42 : 0.32))
                elide: Text.ElideRight
            }
        }
    }

    fullRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.minimumHeight: Kirigami.Units.gridUnit * 14
        Layout.preferredWidth: Kirigami.Units.gridUnit * 22
        Layout.preferredHeight: Kirigami.Units.gridUnit * 18

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: tr("title")
                    font.bold: true
                    font.pointSize: 13
                }
                PlasmaComponents.Button {
                    text: tr("check")
                    enabled: !root.checking
                    onClicked: root.refresh()
                }
            }

            PlasmaComponents.Label {
                Layout.fillWidth: true
                text: root.statusLine
                color: root.statusColor
                wrapMode: Text.WordWrap
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: Kirigami.Units.smallSpacing
                columnSpacing: Kirigami.Units.largeSpacing

                PlasmaComponents.Label { text: tr("queryInterval") }
                PlasmaComponents.Label { text: root.intervalMinutes + " " + tr("minutes") }
                PlasmaComponents.Label { text: tr("balanceThreshold") }
                PlasmaComponents.Label { text: Number(root.thresholdYuan).toFixed(2) + " " + root.totalCurrency }
                PlasmaComponents.Label { text: tr("lastCheck") }
                PlasmaComponents.Label { text: root.lastCheck }
                PlasmaComponents.Label { text: tr("totalBalance") }
                PlasmaComponents.Label {
                    text: root.totalBalance + " " + root.totalCurrency
                    color: root.statusColor
                    font.bold: true
                }
            }

            PlasmaComponents.Label {
                text: tr("balances")
                font.bold: true
                visible: Object.keys(root.balances).length > 0
            }

            Repeater {
                model: Object.keys(root.balances)
                delegate: PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: {
                        var item = root.balances[modelData]
                        return modelData + ": " + tr("totalBalance").toLowerCase() + " "
                            + Number(item.total_balance).toFixed(2)
                            + " (" + tr("toppedUp") + " " + Number(item.topped_up_balance).toFixed(2)
                            + ", " + tr("granted") + " " + Number(item.granted_balance).toFixed(2) + ")"
                    }
                    wrapMode: Text.WordWrap
                }
            }

            Item { Layout.fillHeight: true }
        }
    }
}
