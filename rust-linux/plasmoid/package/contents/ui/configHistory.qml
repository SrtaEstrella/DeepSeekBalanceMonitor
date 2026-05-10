import QtQuick
import QtQuick.Controls as QtControls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as Plasma5Support

Kirigami.FormLayout {
    id: page

    property bool busy: false
    property bool exporting: false
    property string statusText: ""
    property string summaryText: ""
    property var records: []
    property var currencyValues: ["all"]
    property var currencyLabels: [tr("all")]
    property string pageLanguage: systemLanguage()
    readonly property string uiLanguage: pageLanguage

    function systemLanguage() {
        var localeName = Qt.locale().name
        if (!localeName || String(localeName).length === 0) {
            return "zh"
        }
        return String(localeName).indexOf("zh") === 0 ? "zh" : "en"
    }

    function tr(key) {
        var zh = {
            all: "全部",
            chart: "余额趋势",
            currency: "币种",
            days: "天数",
            empty: "暂无余额历史。",
            export: "导出 CSV",
            exportFailed: "导出失败：",
            exported: "已导出：",
            falling: "下降",
            loadFailed: "加载历史失败：",
            loaded: "已加载。",
            loading: "正在加载...",
            range: "范围",
            refresh: "刷新",
            rising: "上升",
            stable: "持平",
            total: "总余额",
            trend: "趋势",
            change: "变化",
            average: "平均",
            xAxis: "时间",
            yAxis: "总余额"
        }
        var en = {
            all: "All",
            chart: "Balance Trend",
            currency: "Currency",
            days: "Days",
            empty: "No balance history.",
            export: "Export CSV",
            exportFailed: "Export failed: ",
            exported: "Exported: ",
            falling: "Falling",
            loadFailed: "Failed to load history: ",
            loaded: "Loaded.",
            loading: "Loading...",
            range: "Range",
            refresh: "Refresh",
            rising: "Rising",
            stable: "Flat",
            total: "Total",
            trend: "Trend",
            change: "Change",
            average: "Average",
            xAxis: "Time",
            yAxis: "Total"
        }
        var table = uiLanguage === "zh" ? zh : en
        return table[key] || key
    }

    function daysValue() {
        var value = parseInt(daysField.text, 10)
        if (isNaN(value)) {
            value = 30
        }
        return Math.max(1, Math.min(3650, value))
    }

    function selectedCurrency() {
        return currencyValues[Math.max(0, currencyBox.currentIndex)] || "all"
    }

    function loadHistory() {
        busy = true
        statusText = tr("loading")
        loader.connectSource("/usr/local/bin/dsmon history json " + daysValue() + " " + selectedCurrency())
    }

    function loadConfig() {
        busy = true
        statusText = tr("loading")
        loader.connectSource("/usr/local/bin/dsmon config-json")
    }

    function exportHistory() {
        exporting = true
        statusText = tr("loading")
        exporter.connectSource("/usr/local/bin/dsmon history export " + daysValue() + " " + selectedCurrency())
    }

    function updateCurrencyOptions(values) {
        var current = selectedCurrency()
        currencyValues = ["all"].concat(values || [])
        currencyLabels = [tr("all")].concat(values || [])
        var index = currencyValues.indexOf(current)
        currencyBox.currentIndex = index >= 0 ? index : 0
    }

    function trendText(value) {
        if (value > 0.000001) {
            return tr("rising")
        }
        if (value < -0.000001) {
            return tr("falling")
        }
        return tr("stable")
    }

    function updateSummary(payload) {
        var summary = payload.summary || []
        if (!summary || summary.length === 0) {
            summaryText = tr("empty")
            return
        }
        var lines = [tr("days") + ": " + payload.days + " | " + tr("currency") + ": " + (payload.currency || tr("all"))]
        for (var i = 0; i < summary.length; i++) {
            var item = summary[i]
            lines.push(item.currency + ": "
                + tr("trend") + " " + trendText(Number(item.change_total)) + " | "
                + tr("total") + " " + Number(item.latest_total).toFixed(2) + " | "
                + tr("range") + " " + Number(item.min_total).toFixed(2) + "-" + Number(item.max_total).toFixed(2) + " | "
                + tr("average") + " " + Number(item.avg_total).toFixed(2) + " | "
                + tr("change") + " " + Number(item.change_total).toFixed(2))
        }
        summaryText = lines.join("\n")
    }

    Component.onCompleted: loadConfig()

    Plasma5Support.DataSource {
        id: loader
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var stdout = data["stdout"] || ""
            var stderr = data["stderr"] || ""
            if (String(sourceName).indexOf("config-json") !== -1) {
                try {
                    var config = JSON.parse(stdout)
                    pageLanguage = config.ui_language === "zh" || config.ui_language === "en" ? config.ui_language : systemLanguage()
                } catch (error) {
                    pageLanguage = systemLanguage()
                }
                disconnectSource(sourceName)
                loadHistory()
                return
            }
            busy = false
            if (stderr.trim().length > 0) {
                statusText = tr("loadFailed") + stderr.trim()
            } else {
                try {
                    var payload = JSON.parse(stdout)
                    records = payload.records || []
                    updateCurrencyOptions(payload.currencies || [])
                    updateSummary(payload)
                    chart.requestPaint()
                    statusText = tr("loaded")
                } catch (error) {
                    statusText = tr("loadFailed") + error
                }
            }
            disconnectSource(sourceName)
        }
    }

    Plasma5Support.DataSource {
        id: exporter
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            exporting = false
            var stdout = data["stdout"] || ""
            var stderr = data["stderr"] || ""
            if (stderr.trim().length > 0) {
                statusText = tr("exportFailed") + stderr.trim()
            } else {
                statusText = tr("exported") + stdout.trim().replace(/^Exported:\s*/, "")
            }
            disconnectSource(sourceName)
        }
    }

    RowLayout {
        Layout.fillWidth: true

        QtControls.Label {
            text: tr("days")
        }
        QtControls.TextField {
            id: daysField
            text: "30"
            Layout.preferredWidth: Kirigami.Units.gridUnit * 4
            onEditingFinished: loadHistory()
        }
        QtControls.Label {
            text: tr("currency")
        }
        QtControls.ComboBox {
            id: currencyBox
            model: page.currencyLabels
            Layout.preferredWidth: Kirigami.Units.gridUnit * 7
            onActivated: loadHistory()
        }
        QtControls.Button {
            text: tr("refresh")
            enabled: !busy
            onClicked: loadHistory()
        }
        QtControls.Button {
            text: tr("export")
            enabled: !exporting
            onClicked: exportHistory()
        }
    }

    QtControls.Label {
        Layout.fillWidth: true
        text: summaryText
        wrapMode: Text.WordWrap
    }

    Canvas {
        id: chart
        Kirigami.FormData.label: tr("chart")
        Layout.fillWidth: true
        Layout.preferredHeight: Kirigami.Units.gridUnit * 14
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.fillStyle = Kirigami.Theme.backgroundColor
            ctx.fillRect(0, 0, width, height)
            if (page.records.length === 0) {
                return
            }
            var points = page.records.slice(Math.max(0, page.records.length - 80))
            var minValue = points[0].total
            var maxValue = points[0].total
            for (var i = 0; i < points.length; i++) {
                minValue = Math.min(minValue, points[i].total)
                maxValue = Math.max(maxValue, points[i].total)
            }
            var span = Math.max(0.01, maxValue - minValue)
            var left = 64
            var right = width - 16
            var top = 12
            var bottom = height - 42
            var plotWidth = Math.max(1, right - left)
            var plotHeight = Math.max(1, bottom - top)
            ctx.strokeStyle = Kirigami.Theme.disabledTextColor
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(left, top)
            ctx.lineTo(left, bottom)
            ctx.lineTo(right, bottom)
            ctx.stroke()
            ctx.fillStyle = Kirigami.Theme.textColor
            ctx.font = "10px sans-serif"
            var midValue = minValue + span / 2
            var labels = [
                { y: top + 4, text: maxValue.toFixed(2) },
                { y: top + plotHeight / 2 + 4, text: midValue.toFixed(2) },
                { y: bottom + 4, text: minValue.toFixed(2) }
            ]
            for (var labelIndex = 0; labelIndex < labels.length; labelIndex++) {
                ctx.fillText(labels[labelIndex].text, 4, labels[labelIndex].y)
            }
            ctx.fillText(tr("yAxis"), 4, top + 16)
            ctx.fillText(points[0].timestamp.substring(5, 16), left, height - 18)
            ctx.fillText(points[points.length - 1].timestamp.substring(5, 16), Math.max(left, right - 80), height - 18)
            ctx.fillText(tr("xAxis"), Math.max(left, right - 40), height - 4)
            ctx.strokeStyle = Kirigami.Theme.highlightColor
            ctx.lineWidth = 2
            ctx.beginPath()
            for (var j = 0; j < points.length; j++) {
                var x = points.length === 1 ? left + plotWidth / 2 : left + j * plotWidth / (points.length - 1)
                var y = bottom - ((points[j].total - minValue) / span) * plotHeight
                if (j === 0) {
                    ctx.moveTo(x, y)
                } else {
                    ctx.lineTo(x, y)
                }
            }
            ctx.stroke()
        }
    }

    QtControls.Label {
        Layout.fillWidth: true
        text: statusText
        wrapMode: Text.WordWrap
    }
}
