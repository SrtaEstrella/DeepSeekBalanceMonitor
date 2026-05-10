import org.kde.plasma.configuration

ConfigModel {
    function systemLanguage() {
        var localeName = Qt.locale().name
        if (!localeName || String(localeName).length === 0) {
            return "zh"
        }
        return String(localeName).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = { general: "常规", history: "历史" }
        var en = { general: "General", history: "History" }
        var table = systemLanguage() === "zh" ? zh : en
        return table[key] || key
    }

    ConfigCategory {
        name: tr("general")
        icon: "configure"
        source: "configGeneral.qml"
    }
    ConfigCategory {
        name: tr("history")
        icon: "view-history"
        source: "configHistory.qml"
    }
}
