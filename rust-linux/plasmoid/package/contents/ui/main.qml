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

    Plasmoid.icon: lowBalance || !ok || !daemonRunning ? "dialog-warning" : "wallet-open"
    Plasmoid.title: tr("title")
    toolTipMainText: compactLabel
    preferredRepresentation: compactRepresentation

    readonly property string compactLabel: ok ? totalBalance : (checking ? "..." : "!")
    readonly property string balanceStatusLine: ok
        ? tr("totalBalance") + ": " + totalBalance + " " + totalCurrency
        : (configured ? errorText : tr("noKey"))
    readonly property string statusLine: daemonChecked && !daemonRunning ? tr("daemonStopped") : balanceStatusLine
    readonly property color statusColor: !configured || !ok || lowBalance || !daemonRunning
        ? Kirigami.Theme.negativeTextColor
        : Kirigami.Theme.positiveTextColor

    function runCommand(command) {
        executable.connectSource(command)
    }

    function systemLanguage() {
        return String(Qt.locale().name).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = {
            title: "DeepSeek 余额监控",
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
            viewBalance: "查看余额",
            checkNow: "立即查询",
            quit: "退出",
            balanceEmpty: "暂无余额数据，请等待或手动查询。",
            balanceErrorTitle: "余额查询失败",
            daemonStopped: "dsmon 后台进程未运行，请启动 dsmon.service。"
        }
        var en = {
            title: "DeepSeek Balance Monitor",
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
            viewBalance: "View Balance",
            checkNow: "Check Now",
            quit: "Quit",
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

    function quitService() {
        runCommand("systemctl --user stop dsmon.service")
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function notificationTitle() {
        if (ok && Object.keys(balances).length > 0) {
            return "DeepSeek: " + totalBalance + " " + totalCurrency
        }
        return ok ? tr("title") : tr("balanceErrorTitle")
    }

    function balanceMessage() {
        var prefix = daemonChecked && !daemonRunning ? tr("daemonStopped") + "\n" : ""
        if (!configured) {
            return prefix + tr("noKey")
        }
        if (!ok) {
            return prefix + (errorText || tr("noOutput"))
        }
        var keys = Object.keys(balances)
        if (keys.length === 0) {
            return prefix + tr("balanceEmpty")
        }
        var lines = []
        for (var i = 0; i < keys.length; i++) {
            var code = keys[i]
            var item = balances[code]
            lines.push(code + ": " + Number(item.total_balance).toFixed(2)
                + " (" + tr("toppedUp") + " " + Number(item.topped_up_balance).toFixed(2)
                + ", " + tr("granted") + " " + Number(item.granted_balance).toFixed(2) + ")")
        }
        lines.push(tr("lastCheck") + ": " + lastCheck)
        return prefix + lines.join("\n")
    }

    function showBalanceNotification() {
        runCommand("/usr/bin/notify-send --app-name " + shellQuote(tr("title"))
            + " --icon " + shellQuote(Plasmoid.icon)
            + " " + shellQuote(notificationTitle())
            + " " + shellQuote(balanceMessage()))
    }

    function updateAttentionStatus() {
        Plasmoid.status = !ok || lowBalance || (daemonChecked && !daemonRunning)
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
            ok = !!status.ok
            lowBalance = !!status.low_balance
            errorText = status.error || ""
            configPath = status.config_path || ""
            intervalMinutes = status.interval_minutes || 10
            thresholdYuan = status.threshold_yuan || 1.0
            language = (!status.configured && status.language === "en") ? systemLanguage() : (status.language || language)
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
                root.updateAttentionStatus()
            } else if (String(sourceName).indexOf("stop dsmon.service") !== -1) {
                root.daemonRunning = false
                root.updateAttentionStatus()
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
            isSeparator: true
        },
        PlasmaCore.Action {
            text: tr("quit")
            icon.name: "application-exit"
            onTriggered: root.quitService()
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
