import QtQuick
import QtQuick.Controls as QtControls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasma5support as Plasma5Support

KCM.SimpleKCM {
    id: page

    property string cfg_language: systemLanguage()
    property string cfg_languageDefault: systemLanguage()
    property bool cfg_expanding: false
    property int cfg_length: 0
    property string statusText: ""
    property bool busy: false
    property bool hasStoredApiKey: false
    property string loadedApiKey: ""
    property bool savingBatch: false
    property var saveCommands: []
    readonly property string uiLanguage: languageCombo.currentValue || systemLanguage()

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function runCommand(command) {
        executable.connectSource(command)
    }

    function queueSetCommand(field, values) {
        var command = "/usr/local/bin/dsmon set " + shellQuote(field)
        for (var index = 0; index < values.length; index++) {
            command += " " + shellQuote(values[index])
        }
        saveCommands.push(command)
    }

    function runNextSaveCommand() {
        if (saveCommands.length === 0) {
            savingBatch = false
            busy = false
            statusText = tr("saved")
            loadConfig()
            return
        }
        runCommand(saveCommands.shift())
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
            apiKeyStored: "********",
            apiKeyUpdateHint: "API Key 已加密保存。修改真实 Key 时请在终端运行 dsmon set-key；如需演示模式，可直接输入 demo 后保存。",
            showApiKey: "API Key 已隐藏",
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
            exportPath: "数据导出路径：",
            proxy: "HTTP/HTTPS 代理：",
            theme: "图标主题：",
            themeDefault: "默认",
            themeContrast: "高对比",
            themeBright: "明亮",
            themeDarkMode: "暗色模式",
            themeMono: "纯灰度",
            themeCustom: "自定义",
            iconStroke: "图标描边",
            colorOk: "正常色",
            colorLow: "低余额色",
            colorDegraded: "服务异常色",
            colorNoData: "无数据色",
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
            apiKeyStored: "********",
            apiKeyUpdateHint: "API key is stored encrypted. To update a real key, run dsmon set-key in a terminal. For demo mode, enter demo here and save.",
            showApiKey: "API key hidden",
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
            exportPath: "Export path:",
            proxy: "HTTP/HTTPS proxy:",
            theme: "Icon theme:",
            themeDefault: "Default",
            themeContrast: "High Contrast",
            themeBright: "Bright",
            themeDarkMode: "Dark Mode",
            themeMono: "Monochrome",
            themeCustom: "Custom",
            iconStroke: "Icon stroke",
            colorOk: "OK color",
            colorLow: "Low color",
            colorDegraded: "Degraded color",
            colorNoData: "No data color",
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
        if (apiKeyField.text.trim().length === 0 && !hasStoredApiKey) {
            statusText = tr("apiKeyRequired")
            return
        }
        var threshold = thresholdField.text.trim()
        if (threshold.length === 0) {
            statusText = tr("thresholdRequired")
            return
        }
        var apiKeyArg = ""
        if (apiKeyField.text.trim() !== loadedApiKey.trim()) {
            if (apiKeyField.text.trim().toLowerCase() === "demo") {
                apiKeyArg = "demo"
            } else {
                statusText = tr("apiKeyUpdateHint")
                busy = false
                return
            }
        }
        busy = true
        statusText = tr("saving")
        saveCommands = []
        if (apiKeyArg === "demo") {
            saveCommands.push("/usr/local/bin/dsmon set-key " + shellQuote("demo"))
        }
        queueSetCommand("interval", [String(intervalSpin.value)])
        queueSetCommand("threshold", [threshold])
        queueSetCommand("ui-language", [languageCombo.currentValue])
        queueSetCommand("auto-start", [autoStartCheck.checked ? "true" : "false"])
        queueSetCommand("alert-mode", [alertModeCombo.currentValue])
        queueSetCommand("api-alert-enabled", [apiAlertCheck.checked ? "true" : "false"])
        queueSetCommand("retention-days", [String(logRetentionSpin.value)])
        queueSetCommand("export-path", [exportPathField.text.trim()])
        queueSetCommand("http-proxy", [proxyField.text.trim()])
        queueSetCommand("theme", [themeCombo.currentValue])
        queueSetCommand("icon-stroke", [iconStrokeCheck.checked ? "true" : "false"])
        if (themeCombo.currentValue === "custom") {
            queueSetCommand("icon-colors", [
                okColorField.text.trim(),
                lowColorField.text.trim(),
                degradedColorField.text.trim(),
                noDataColorField.text.trim()
            ])
        }
        savingBatch = true
        runNextSaveCommand()
    }

    function applyConfig(stdout) {
        var config = JSON.parse(stdout)
        hasStoredApiKey = !!config.has_key || (config.api_key || "").length > 0 || config.api_key === "masked"
        loadedApiKey = hasStoredApiKey ? tr("apiKeyStored") : ""
        apiKeyField.text = loadedApiKey
        apiKeyField.placeholderText = hasStoredApiKey ? tr("apiKeyStored") : "dsmon set-key"
        intervalSpin.value = config.interval_minutes || 10
        thresholdField.text = Number(config.threshold_yuan === undefined ? 1.0 : config.threshold_yuan).toFixed(2)
        autoStartCheck.checked = !!config.auto_start
        var alertIndex = alertModeCombo.indexOfValue(config.alert_mode || "once")
        alertModeCombo.currentIndex = alertIndex >= 0 ? alertIndex : 0
        apiAlertCheck.checked = config.api_alert_enabled === undefined ? true : !!config.api_alert_enabled
        logRetentionSpin.value = config.retention_days || 30
        exportPathField.text = config.export_path || ""
        proxyField.text = config.http_proxy || ""
        var themeIndex = themeCombo.indexOfValue(config.theme || "default")
        themeCombo.currentIndex = themeIndex >= 0 ? themeIndex : 0
        iconStrokeCheck.checked = !!config.icon_stroke
        var colors = config.icon_colors || {}
        okColorField.text = colors.ok || "3c6966"
        lowColorField.text = colors.low || "b9463c"
        degradedColorField.text = colors.degraded || "78695a"
        noDataColorField.text = colors.nodata || "69696e"
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
            var stdout = data["stdout"] || ""
            var stderr = data["stderr"] || ""
            if (String(sourceName).indexOf("config-json") !== -1) {
                busy = false
                try {
                    applyConfig(stdout)
                } catch (error) {
                    statusText = tr("loadFailed") + error
                }
            } else if (savingBatch) {
                if (stderr.trim().length > 0) {
                    saveCommands = []
                    savingBatch = false
                    busy = false
                    statusText = tr("saveFailed") + stderr.trim()
                } else {
                    runNextSaveCommand()
                }
            }
            disconnectSource(sourceName)
        }
    }

    Kirigami.FormLayout {
        QtControls.TextField {
            id: apiKeyField
            Kirigami.FormData.label: tr("apiKey")
            Layout.fillWidth: true
            echoMode: TextInput.Password
        }

        QtControls.CheckBox {
            id: showKeyCheck
            text: tr("showApiKey")
            visible: false
        }

        QtControls.Label {
            Layout.fillWidth: true
            text: tr("apiKeyUpdateHint")
            wrapMode: Text.WordWrap
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

        QtControls.TextField {
            id: exportPathField
            Kirigami.FormData.label: tr("exportPath")
            Layout.fillWidth: true
            placeholderText: "$HOME"
        }

        QtControls.TextField {
            id: proxyField
            Kirigami.FormData.label: tr("proxy")
            Layout.fillWidth: true
            placeholderText: "http://127.0.0.1:7890"
        }

        QtControls.ComboBox {
            id: themeCombo
            Kirigami.FormData.label: tr("theme")
            textRole: "text"
            valueRole: "value"
            model: [
                { text: tr("themeDefault"), value: "default" },
                { text: tr("themeContrast"), value: "contrast" },
                { text: tr("themeBright"), value: "bright" },
                { text: tr("themeDarkMode"), value: "dark_mode" },
                { text: tr("themeMono"), value: "mono" },
                { text: tr("themeCustom"), value: "custom" }
            ]
        }

        QtControls.CheckBox {
            id: iconStrokeCheck
            text: tr("iconStroke")
        }

        QtControls.TextField {
            id: okColorField
            Kirigami.FormData.label: tr("colorOk")
            Layout.fillWidth: true
            placeholderText: "3c6966"
        }

        QtControls.TextField {
            id: lowColorField
            Kirigami.FormData.label: tr("colorLow")
            Layout.fillWidth: true
            placeholderText: "b9463c"
        }

        QtControls.TextField {
            id: degradedColorField
            Kirigami.FormData.label: tr("colorDegraded")
            Layout.fillWidth: true
            placeholderText: "78695a"
        }

        QtControls.TextField {
            id: noDataColorField
            Kirigami.FormData.label: tr("colorNoData")
            Layout.fillWidth: true
            placeholderText: "69696e"
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
}
