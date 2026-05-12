import QtQuick
import QtQuick.Controls as QtControls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import org.kde.plasma.plasma5support as Plasma5Support

KCM.SimpleKCM {
    id: page

    property bool busy: false
    property bool exporting: false
    property string statusText: ""
    property string summaryText: ""
    property var records: []
    property var currencyValues: ["all"]
    property var currencyLabels: [tr("all")]
    property string pageLanguage: systemLanguage()
    property string cfg_language: pageLanguage
    property string cfg_languageDefault: systemLanguage()
    property bool cfg_expanding: false
    property int cfg_length: 0
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
            dailyRate: "日均消耗",
            estimated: "预计可用",
            notEnoughData: "数据不足，无法计算消耗速率",
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
            dailyRate: "Avg",
            estimated: "Est.",
            notEnoughData: "Not enough data to estimate consumption",
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
        if (payload.consumption_rate) {
            var rate = payload.consumption_rate
            var hoursLeft = Number(rate.hours_left)
            var daysLeft = Math.floor(hoursLeft / 24)
            var hoursRemainder = Math.floor(hoursLeft % 24)
            lines.push(tr("dailyRate") + " " + Number(rate.daily_rate).toFixed(2) + " " + rate.currency
                + (uiLanguage === "zh" ? " | " + tr("estimated") + " " + daysLeft + " 天 " + hoursRemainder + " 小时"
                    : "/day | " + tr("estimated") + " " + daysLeft + "d " + hoursRemainder + "h remaining"))
        } else {
            lines.push(tr("notEnoughData"))
        }
        summaryText = lines.join("\n")
    }

    function repaintChart() {}

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
            if (stderr.trim().length > 0 && stdout.trim().length === 0) {
                statusText = tr("loadFailed") + stderr.trim()
            } else {
                try {
                    var payload = JSON.parse(stdout)
                    records = payload.records || []
                    updateCurrencyOptions(payload.currencies || [])
                    updateSummary(payload)
                    statusText = stderr.trim().length > 0 ? stderr.trim() : tr("loaded")
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

    Kirigami.FormLayout {
        RowLayout {
            Layout.fillWidth: true

            QtControls.Label {
                text: tr("days")
            }
            QtControls.TextField {
                id: daysField
                text: "30"
                Layout.preferredWidth: Kirigami.Units.gridUnit * 4
                onAccepted: loadHistory()
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

        QtControls.Control {
            id: chartFrame
            Kirigami.FormData.label: tr("chart")
            Layout.fillWidth: true
            implicitWidth: Kirigami.Units.gridUnit * 30
            implicitHeight: Kirigami.Units.gridUnit * 14
            clip: true
            padding: 0

            property var points: page.records.slice(Math.max(0, page.records.length - 80))
            readonly property bool hasPoints: points.length > 0
            readonly property real plotLeft: 64
            readonly property real plotRight: Math.max(plotLeft + 1, width - 16)
            readonly property real plotTop: 12
            readonly property real plotBottom: Math.max(plotTop + 1, height - 42)
            readonly property real plotWidth: Math.max(1, plotRight - plotLeft)
            readonly property real plotHeight: Math.max(1, plotBottom - plotTop)
            readonly property real minValue: hasPoints ? minTotal() : 0
            readonly property real maxValue: hasPoints ? maxTotal() : 1
            readonly property real visualMinValue: hasPoints && Math.abs(maxValue - minValue) < 0.01 ? minValue - 0.01 : minValue
            readonly property real visualMaxValue: hasPoints && Math.abs(maxValue - minValue) < 0.01 ? maxValue + 0.01 : maxValue
            readonly property real span: Math.max(0.01, visualMaxValue - visualMinValue)
            readonly property real barWidth: Math.max(2, Math.min(12, plotWidth / Math.max(1, points.length) * 0.65))

            function minTotal() {
                var value = Number(points[0].total)
                for (var i = 1; i < points.length; i++) {
                    value = Math.min(value, Number(points[i].total))
                }
                return value
            }

            function maxTotal() {
                var value = Number(points[0].total)
                for (var i = 1; i < points.length; i++) {
                    value = Math.max(value, Number(points[i].total))
                }
                return value
            }

            function xForIndex(index) {
                return points.length === 1 ? plotLeft + plotWidth / 2 : plotLeft + index * plotWidth / (points.length - 1)
            }

            function yForTotal(total) {
                return plotBottom - ((Number(total) - visualMinValue) / span) * plotHeight
            }

            function yLabel(index) {
                if (index === 0) {
                    return visualMaxValue.toFixed(2)
                }
                if (index === 1) {
                    return (visualMinValue + span / 2).toFixed(2)
                }
                return visualMinValue.toFixed(2)
            }

            function yLabelY(index) {
                if (index === 0) {
                    return plotTop - 2
                }
                if (index === 1) {
                    return plotTop + plotHeight / 2 - 7
                }
                return plotBottom - 12
            }

            function dateLabel(timestamp) {
                var text = String(timestamp || "")
                return text.length >= 16 ? text.substring(5, 16) : text
            }

            background: Rectangle {
                color: Kirigami.Theme.backgroundColor
                border.color: Kirigami.Theme.disabledTextColor
                border.width: 1
                opacity: 0.28
            }

            contentItem: Item {
                clip: true

                Rectangle {
                    x: chartFrame.plotLeft
                    y: chartFrame.plotTop
                    width: 1
                    height: chartFrame.plotHeight
                    color: Kirigami.Theme.disabledTextColor
                }

                Rectangle {
                    x: chartFrame.plotLeft
                    y: chartFrame.plotBottom
                    width: chartFrame.plotWidth
                    height: 1
                    color: Kirigami.Theme.disabledTextColor
                }

                Repeater {
                    model: 3
                    Rectangle {
                        x: chartFrame.plotLeft
                        y: chartFrame.yLabelY(index) + 7
                        width: chartFrame.plotWidth
                        height: 1
                        color: Kirigami.Theme.disabledTextColor
                        opacity: 0.22
                    }
                }

                Repeater {
                    model: 3
                    QtControls.Label {
                        x: 4
                        y: chartFrame.yLabelY(index)
                        width: chartFrame.plotLeft - 8
                        height: 14
                        horizontalAlignment: Text.AlignRight
                        font.pixelSize: 10
                        text: chartFrame.yLabel(index)
                    }
                }

                QtControls.Label {
                    x: 4
                    y: chartFrame.plotTop + 12
                    font.pixelSize: 10
                    text: tr("yAxis")
                }

                QtControls.Label {
                    width: 90
                    height: 14
                    x: chartFrame.plotLeft
                    y: parent.height - 28
                    visible: chartFrame.hasPoints
                    color: Kirigami.Theme.textColor
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    text: chartFrame.hasPoints ? chartFrame.dateLabel(chartFrame.points[0].timestamp) : ""
                }

                QtControls.Label {
                    width: 90
                    height: 14
                    x: Math.max(chartFrame.plotLeft, Math.min(parent.width - width, chartFrame.plotRight - width))
                    y: parent.height - 28
                    visible: chartFrame.hasPoints
                    color: Kirigami.Theme.textColor
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignRight
                    elide: Text.ElideRight
                    text: chartFrame.hasPoints ? chartFrame.dateLabel(chartFrame.points[chartFrame.points.length - 1].timestamp) : ""
                }

                QtControls.Label {
                    width: 40
                    height: 14
                    x: Math.max(chartFrame.plotLeft, Math.min(parent.width - width, chartFrame.plotRight - width))
                    y: parent.height - 14
                    color: Kirigami.Theme.textColor
                    font.pixelSize: 10
                    horizontalAlignment: Text.AlignRight
                    text: tr("xAxis")
                }

                Repeater {
                    model: chartFrame.hasPoints ? chartFrame.points.length : 0
                    Rectangle {
                        readonly property real totalValue: Number(chartFrame.points[index].total)
                        width: chartFrame.barWidth
                        height: Math.max(2, chartFrame.plotBottom - chartFrame.yForTotal(totalValue))
                        x: Math.max(chartFrame.plotLeft, Math.min(chartFrame.plotRight - width, chartFrame.xForIndex(index) - width / 2))
                        y: chartFrame.plotBottom - height
                        color: Kirigami.Theme.highlightColor
                        opacity: 0.32
                    }
                }

                Repeater {
                    model: chartFrame.hasPoints ? chartFrame.points.length : 0
                    Rectangle {
                        width: 6
                        height: 6
                        radius: 3
                        x: chartFrame.xForIndex(index) - width / 2
                        y: chartFrame.yForTotal(chartFrame.points[index].total) - height / 2
                        color: Kirigami.Theme.highlightColor
                        border.color: Kirigami.Theme.backgroundColor
                        border.width: 1
                    }
                }

                QtControls.Label {
                    anchors.centerIn: parent
                    visible: !chartFrame.hasPoints
                    opacity: 0.7
                    text: tr("empty")
                }
            }
        }

        QtControls.Label {
            Layout.fillWidth: true
            text: statusText
            wrapMode: Text.WordWrap
        }
    }
}
