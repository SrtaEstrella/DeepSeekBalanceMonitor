class ApiClient {
    constructor() {
        this._available = typeof window.pywebview !== 'undefined'
            && window.pywebview.api
            && Object.keys(window.pywebview.api).length > 0;
    }

    async _ensureReady() {
        if (window.pywebview && window.pywebview.api) return true;
        return new Promise(resolve => {
            window.addEventListener('pywebviewready', () => resolve(true), {once: true});
            setTimeout(() => resolve(false), 2000);
        });
    }

    async _call(method, ...args) {
        const ready = await this._ensureReady();
        if (!ready) {
            return { success: false, error: 'PyWebView not available' };
        }
        try {
            return await window.pywebview.api[method](...args);
        } catch (err) {
            console.error(`API ${method} error:`, err);
            return { success: false, error: err.message };
        }
    }

    async getSettings() { return this._call('get_settings'); }
    async saveSettings(settings) { return this._call('save_settings', settings); }
    async getI18n(lang) { return this._call('get_i18n', lang); }
    async selectDirectory() { return this._call('select_directory'); }

    async getHistoryPage(limit, offset) { return this._call('get_history_page', limit, offset); }
    async getConsumptionRate() { return this._call('get_consumption_rate'); }
    async exportCsv() { return this._call('export_csv'); }
    async open_url(url) { return this._call('open_url', url); }
    async getApiStatus() { return this._call('get_api_status'); }
}

window.api = new ApiClient();
