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
        var localeName = Qt.locale().name
        if (!localeName || String(localeName).length === 0) {
            return "zh"
        }
        return String(localeName).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = {
            loading: "正在加载...",
            saving: "正在保存...",
            loaded: "已加载。",
            saved: "已保存。",
            saveFailed: "保存失败：",
            apiKeyRequired: "DeepSeek API Key 不能为空。",
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
            alerts: "低余额提醒：",
            alertNever: "不提醒",
            alertAlways: "持续提醒",
            alertOnce: "仅提醒一次",
            apiAlert: "API 服务状态变化提醒",
            logRetention: "日志和记录保留天数：",
            days: "天",
            save: "保存"
        }
        var en = {
            loading: "Loading...",
            saving: "Saving...",
            loaded: "Loaded.",
            saved: "Saved.",
            saveFailed: "Failed to save: ",
            apiKeyRequired: "DeepSeek API Key is required.",
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
            alerts: "Low Balance Alert:",
            alertNever: "Never",
            alertAlways: "Always",
            alertOnce: "Once",
            apiAlert: "API service status alerts",
            logRetention: "Log & record retention (days):",
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
        if (apiKeyField.text.trim().length === 0) {
            statusText = tr("apiKeyRequired")
            return
        }
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
            + " " + shellQuote(alertModeCombo.currentValue)
            + " " + (apiAlertCheck.checked ? "true" : "false")
            + " " + logRetentionSpin.value)
    }

    function applyConfig(stdout) {
        var config = JSON.parse(stdout)
        apiKeyField.text = config.api_key || ""
        intervalSpin.value = config.interval_minutes || 10
        thresholdField.text = Number(config.threshold_yuan === undefined ? 1.0 : config.threshold_yuan).toFixed(2)
        autoStartCheck.checked = !!config.auto_start
        var alertIndex = alertModeCombo.indexOfValue(config.alert_mode || "once")
        alertModeCombo.currentIndex = alertIndex >= 0 ? alertIndex : 0
        apiAlertCheck.checked = config.api_alert_enabled === undefined ? true : !!config.api_alert_enabled
        logRetentionSpin.value = config.retention_days || 30
        var selectedLanguage = config.ui_language === "zh" || config.ui_language === "en" ? config.ui_language : systemLanguage()
        var index = languageCombo.indexOfValue(selectedLanguage)
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
                statusText = stderr.trim().length > 0 ? tr("saveFailed") + stderr.trim() : tr("saved")
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

    QtControls.ComboBox {
        id: alertModeCombo
        Kirigami.FormData.label: tr("alerts")
        textRole: "text"
        valueRole: "value"
        model: [
            { text: tr("alertOnce"), value: "once" },
            { text: tr("alertAlways"), value: "always" },
            { text: tr("alertNever"), value: "never" }
        ]
    }

    QtControls.CheckBox {
        id: apiAlertCheck
        text: tr("apiAlert")
    }

    QtControls.SpinBox {
        id: logRetentionSpin
        Kirigami.FormData.label: tr("logRetention")
        from: 1
        to: 3650
        editable: true
        textFromValue: function(value) { return value + " " + tr("days") }
        valueFromText: function(text) { return parseInt(text) || 30 }
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
