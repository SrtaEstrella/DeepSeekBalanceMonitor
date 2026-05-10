class BalanceChart {
    constructor() {
        this.chart = null;
        this.data = [];
        this.selectedDate = '';

        const dateFilter = document.getElementById('history-date-filter');
        if (dateFilter) {
            dateFilter.addEventListener('change', (e) => {
                this.selectedDate = e.target.value;
                this._renderTable();
            });
        }

        const exportBtn = document.getElementById('btn-export-csv');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this._exportCsv());
        }
    }

    async init() {
        await this._load();
    }

    async refresh() {
        await this._load();
    }

    async _load() {
        const [historyRes, rateRes] = await Promise.all([
            window.api.getHistoryPage(500, 0),
            window.api.getConsumptionRate(),
        ]);

        if (historyRes && historyRes.success) {
            this.data = historyRes.data || [];
        }

        this._renderChart();
        this._renderTable();
        this._renderRateInfo(rateRes);
    }

    _renderChart() {
        const canvas = document.getElementById('balance-chart');
        const ctx = canvas.getContext('2d');

        // 1. Filter out all-zero records
        let records = this.data.filter(r => {
            const tStr = r.total.toFixed(4);
            const tpStr = r.topped.toFixed(4);
            const gStr = (r.granted || 0).toFixed(4);
            return !(tStr === '0.0000' && tpStr === '0.0000' && gStr === '0.0000');
        });

        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        if (records.length === 0) {
            return;
        }

        // 2. Filter 72 hours from the latest record
        const latestTimeStr = records[0].timestamp; // "YYYY-MM-DD HH:MM:SS"
        const latestTime = new Date(latestTimeStr.replace(' ', 'T')).getTime();
        const cutoffTime = latestTime - (72 * 60 * 60 * 1000);

        records = records.filter(r => {
            const t = new Date(r.timestamp.replace(' ', 'T')).getTime();
            return t >= cutoffTime;
        });

        // oldest first for chart
        records = records.slice().reverse();

        const labels = records.map(r => {
            const d = r.timestamp.split(' ');
            return d.length > 1 ? d[1].slice(0, 5) : r.timestamp;
        });

        const totals = records.map(r => r.total);

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Total',
                        data: totals,
                        borderColor: '#3C6966',
                        backgroundColor: 'rgba(60,105,102,0.1)',
                        fill: true,
                        tension: 0.2,
                        pointRadius: 1.5,
                        pointHoverRadius: 4,
                        borderWidth: 1.5,
                    }
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: {
                        display: true,
                        labels: {
                            color: '#888',
                            boxWidth: 12,
                            padding: 8,
                            font: { size: 13, family: "Inter, sans-serif" },
                        },
                    },
                    tooltip: {
                        backgroundColor: '#252525',
                        titleColor: '#e0e0e0',
                        bodyColor: '#e0e0e0',
                        borderColor: '#3a3a3a',
                        borderWidth: 1,
                        padding: 10,
                        bodyFont: { size: 14, family: "Inter, sans-serif" },
                        titleFont: { size: 13, family: "Inter, sans-serif" },
                        callbacks: {
                            label: ctx => {
                                const val = ctx.raw.toFixed(4);
                                return ` ${ctx.dataset.label}: ${val}`;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        display: true,
                        afterFit: (axis) => {
                            axis.height = Math.max(axis.height, 60);
                        },
                        ticks: {
                            color: '#888',
                            font: { size: 13, family: "Inter, sans-serif" },
                            padding: 8,
                            maxTicksLimit: 10,
                            autoSkip: true,
                        },
                        grid: {
                            display: true,
                            color: 'rgba(128,128,128,0.15)',
                        },
                    },
                    y: {
                        display: true,
                        grace: '10%',
                        ticks: {
                            color: '#888',
                            font: { size: 13, family: "Inter, sans-serif" },
                            callback: v => v.toFixed(2),
                            padding: 8,
                        },
                        grid: {
                            display: true,
                            color: 'rgba(128,128,128,0.15)',
                        },
                    },
                },
            },
        });
    }

    _renderTable() {
        const tbody = document.getElementById('table-body');
        tbody.innerHTML = '';

        let validRows = [];
        const prevNumsByCurrency = {};

        // this.data is newest-first. We iterate from oldest to newest to detect changes per currency.
        for (let i = this.data.length - 1; i >= 0; i--) {
            const r = this.data[i];
            const tStr = r.total.toFixed(4);
            const tpStr = r.topped.toFixed(4);
            const gStr = (r.granted || 0).toFixed(4);

            if (tStr === '0.0000' && tpStr === '0.0000' && gStr === '0.0000') {
                continue; // Skip all-zero
            }

            const currentNums = `${tStr}_${tpStr}_${gStr}`;
            const currency = r.currency || 'UNKNOWN';

            if (prevNumsByCurrency[currency] !== currentNums) {
                validRows.unshift(r); // push to front so the final array is newest-first
                prevNumsByCurrency[currency] = currentNums;
            }
        }

        if (this.selectedDate) {
            validRows = validRows.filter(r => r.timestamp.startsWith(this.selectedDate));
        }

        for (const r of validRows) {
            const tr = document.createElement('tr');
            const status = r.service_status || '';
            const statusClass = status === 'ok' ? 'status-ok'
                : status === 'low' ? 'status-low'
                    : status === 'degraded' ? 'status-degraded'
                        : 'status-nodata';

            tr.innerHTML = `
                <td>${this._fmtTime(r.timestamp)}</td>
                <td>${r.currency || ''}</td>
                <td class="num">${r.total.toFixed(4)}</td>
                <td class="num">${r.topped.toFixed(4)}</td>
                <td class="num">${(r.granted || 0).toFixed(4)}</td>
                <td class="${statusClass}">${status || '-'}</td>
            `;
            tbody.appendChild(tr);
        }

        if (validRows.length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted)">No data</td>';
            tbody.appendChild(tr);
        }
    }

    _renderRateInfo(rateRes) {
        const el = document.getElementById('rate-info');
        if (rateRes && rateRes.success && rateRes.data) {
            const d = rateRes.data;
            el.innerHTML = `
                <div><span class="rate-value">${d.daily_rate} ${d.currency}/day</span></div>
                <div>≈ ${d.hours_left}h remaining</div>
            `;
        } else {
            el.innerHTML = '';
        }
    }

    async _exportCsv() {
        const result = await window.api.exportCsv();
        if (result && result.success) {
            alert(`Exported ${result.data.count} records to ${result.data.path}`);
        } else {
            const msg = result && result.error ? result.error : 'Export failed';
            if (msg !== 'Cancelled') alert(msg);
        }
    }

    _fmtTime(ts) {
        if (!ts) return '';
        const parts = ts.split(' ');
        if (parts.length >= 2) {
            const d = parts[0].slice(5); // MM-DD
            const t = parts[1].slice(0, 5); // HH:MM
            return `${d} ${t}`;
        }
        return ts;
    }
}
