import QtQuick
import QtQuick.Controls as QtControls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support

Kirigami.FormLayout {
    id: page

    property alias cfg_language: languageCombo.currentValue
    property string statusText: ""
    property bool busy: false
    readonly property string uiLanguage: languageCombo.currentValue || systemLanguage()

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function runCommand(command) {
        executable.connectSource(command)
    }

    function systemLanguage() {
        return String(Qt.locale().name).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = {
            loading: "正在加载...",
            saving: "正在保存...",
            loaded: "已加载。",
            saved: "已保存。",
            thresholdRequired: "余额预警线不能为空。",
            loadFailed: "加载配置失败：",
            apiKey: "DeepSeek API Key:",
            showApiKey: "显示 API Key",
            interval: "查询间隔：",
            minutes: "分钟",
            threshold: "余额预警线：",
            language: "语言 / Language:",
            autoStart: "开机自启动",
            autoStartHint: "请保持开启，使 dsmon 登录后自动启动；Plasma 小工具需要该进程持续运行。",
            alerts: "启用余额预警提醒",
            logRetention: "日志保留：",
            days: "天",
            save: "保存"
        }
        var en = {
            loading: "Loading...",
            saving: "Saving...",
            loaded: "Loaded.",
            saved: "Saved.",
            thresholdRequired: "Balance threshold is required.",
            loadFailed: "Failed to load config: ",
            apiKey: "DeepSeek API Key:",
            showApiKey: "Show API key",
            interval: "Check interval:",
            minutes: "minutes",
            threshold: "Low balance threshold:",
            language: "Language / 语言:",
            autoStart: "Auto-start on boot",
            autoStartHint: "Keep this enabled so dsmon starts after login; the Plasma widget needs this process to stay updated.",
            alerts: "Enable balance alerts",
            logRetention: "Log retention:",
            days: "days",
            save: "Save"
        }
        var table = uiLanguage === "zh" ? zh : en
        return table[key] || key
    }

    function loadConfig() {
        busy = true
        statusText = tr("loading")
        runCommand("/usr/local/bin/dsmon config-json")
    }

    function saveConfig() {
        var threshold = thresholdField.text.trim()
        if (threshold.length === 0) {
            statusText = tr("thresholdRequired")
            return
        }
        busy = true
        statusText = tr("saving")
        runCommand("/usr/local/bin/dsmon set-config "
            + shellQuote(apiKeyField.text)
            + " " + intervalSpin.value
            + " " + shellQuote(threshold)
            + " " + shellQuote(languageCombo.currentValue)
            + " " + (autoStartCheck.checked ? "true" : "false")
            + " " + (alertsCheck.checked ? "true" : "false")
            + " " + logRetentionSpin.value)
    }

    function applyConfig(stdout) {
        var config = JSON.parse(stdout)
        apiKeyField.text = config.api_key || ""
        intervalSpin.value = config.interval_minutes || 10
        thresholdField.text = Number(config.threshold_yuan === undefined ? 1.0 : config.threshold_yuan).toFixed(2)
        autoStartCheck.checked = !!config.auto_start
        alertsCheck.checked = config.enable_alerts !== false
        logRetentionSpin.value = config.log_retention_days || 7
        var defaultLanguage = config.api_key ? (cfg_language || "en") : systemLanguage()
        var index = languageCombo.indexOfValue(config.language === "en" && !config.api_key
            ? defaultLanguage
            : (config.language || defaultLanguage))
        languageCombo.currentIndex = index >= 0 ? index : 0
        statusText = tr("loaded")
    }

    Component.onCompleted: {
        var index = languageCombo.indexOfValue(systemLanguage())
        if (index >= 0) {
            languageCombo.currentIndex = index
        }
        loadConfig()
    }

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            busy = false
            var stdout = data["stdout"] || ""
            var stderr = data["stderr"] || ""
            if (String(sourceName).indexOf("config-json") !== -1) {
                try {
                    applyConfig(stdout)
                } catch (error) {
                    statusText = tr("loadFailed") + error
                }
            } else if (String(sourceName).indexOf("set-config") !== -1) {
                statusText = stderr.trim().length > 0 ? stderr.trim() : tr("saved")
                if (stderr.trim().length === 0) {
                    loadConfig()
                }
            }
            disconnectSource(sourceName)
        }
    }

    QtControls.TextField {
        id: apiKeyField
        Kirigami.FormData.label: tr("apiKey")
        Layout.fillWidth: true
        echoMode: showKeyCheck.checked ? TextInput.Normal : TextInput.Password
    }

    QtControls.CheckBox {
        id: showKeyCheck
        text: tr("showApiKey")
    }

    QtControls.SpinBox {
        id: intervalSpin
        Kirigami.FormData.label: tr("interval")
        from: 1
        to: 1440
        editable: true
        textFromValue: function(value) { return value + " " + tr("minutes") }
        valueFromText: function(text) { return parseInt(text) || 10 }
    }

    QtControls.TextField {
        id: thresholdField
        Kirigami.FormData.label: tr("threshold")
        inputMethodHints: Qt.ImhFormattedNumbersOnly
    }

    QtControls.ComboBox {
        id: languageCombo
        Kirigami.FormData.label: tr("language")
        textRole: "text"
        valueRole: "value"
        model: [
            { text: "English", value: "en" },
            { text: "中文", value: "zh" }
        ]
    }

    QtControls.CheckBox {
        id: autoStartCheck
        text: tr("autoStart")
    }

    QtControls.Label {
        Layout.fillWidth: true
        text: tr("autoStartHint")
        wrapMode: Text.WordWrap
    }

    QtControls.CheckBox {
        id: alertsCheck
        text: tr("alerts")
    }

    QtControls.SpinBox {
        id: logRetentionSpin
        Kirigami.FormData.label: tr("logRetention")
        from: 1
        to: 3650
        editable: true
        textFromValue: function(value) { return value + " " + tr("days") }
        valueFromText: function(text) { return parseInt(text) || 7 }
    }

    QtControls.Button {
        text: tr("save")
        enabled: !busy
        onClicked: saveConfig()
    }

    QtControls.Label {
        Layout.fillWidth: true
        text: statusText
        wrapMode: Text.WordWrap
    }
}
