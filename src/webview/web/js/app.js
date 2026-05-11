class App {
    constructor() {
        this.currentView = 'chart';
        this.settingsUI = new SettingsUI();
        this.chartUI = null;
    }

    async init() {
        // Load settings first to determine correct user language
        const settingsRes = await window.api.getSettings();
        let lang = this._guessLang();
        if (settingsRes && settingsRes.success && settingsRes.data && settingsRes.data.language) {
            lang = settingsRes.data.language;
        }

        // Load translations
        await this.updateI18n(lang);

        // Init settings (loads config, populates form, binds events)
        this.settingsUI.app = this; // Link back to app
        await this.settingsUI.init();

        // Init chart
        this.chartUI = new BalanceChart();
        await this.chartUI.init();

        // Bind tab navigation
        this._bindTabs();

        // Bind global actions
        this._bindGlobalActions();

        // Initial status update
        this._updateApiStatus();
        // Update every 5 minutes
        setInterval(() => this._updateApiStatus(), 300000);

        // Animate in
        document.querySelector('.view-section.active')?.classList.add('animate-in');
    }

    async updateI18n(lang) {
        const i18nRes = await window.api.getI18n(lang);
        let i18n = {};
        if (i18nRes && i18nRes.success === undefined) {
            i18n = i18nRes;
        } else if (i18nRes && i18nRes.data) {
            i18n = i18nRes.data;
        }
        this.i18n = i18n;
        this.settingsUI.i18n = i18n;
        
        this._applyI18n(i18n);
        this._updateApiStatus(); // Refresh status text with new translations
    }

    async _updateApiStatus() {
        const res = await window.api.getApiStatus();
        const dot = document.querySelector('.status-dot');
        const valEl = document.getElementById('api-status-val');
        
        if (res && res.success && res.data) {
            const indicator = res.data.indicator || 'none';
            // Reset classes
            dot.className = 'status-dot';
            dot.classList.add(indicator === 'none' ? 'ok' : indicator);
            
            if (valEl) {
                const transKey = res.trans_key || `status_${indicator}`;
                valEl.textContent = this.i18n[transKey] || indicator;
            }
        }
    }

    _bindGlobalActions() {
        const btnTopup = document.getElementById('btn-topup');
        if (btnTopup) {
            btnTopup.addEventListener('click', () => {
                window.api.open_url('https://platform.deepseek.com/top_up');
            });
        }
    }

    _guessLang() {
        const html = document.documentElement.lang;
        return html === 'zh-CN' ? 'zh' : 'en';
    }

    _applyI18n(i18n) {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.dataset.i18n;
            if (i18n[key]) {
                el.textContent = i18n[key];
            }
        });
        const titleKey = 'settings_title';
        if (i18n[titleKey]) {
            document.title = i18n[titleKey];
        }
    }

    _bindTabs() {
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const viewId = btn.dataset.view;
                this.switchView(viewId);
            });
        });
    }

    switchView(viewId) {
        // Guard unsaved settings when leaving settings
        if (this.currentView === 'settings' && viewId !== 'settings' && this.settingsUI.dirty) {
            const msg = this.i18n['unsaved_changes'] || 'Unsaved changes will be lost. Continue?';
            if (!confirm(msg)) return;
        }

        // Update nav tabs
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelector(`.nav-btn[data-view="${viewId}"]`)?.classList.add('active');

        // Show target view
        document.querySelectorAll('.view-section').forEach(s => {
            s.classList.remove('active', 'animate-in');
        });
        const target = document.getElementById(`${viewId}-view`);
        if (target) {
            target.classList.add('active', 'animate-in');
        }

        this.currentView = viewId;

        // Refresh chart data when switching to chart tab
        if (viewId === 'chart' && this.chartUI) {
            this.chartUI.refresh();
        }
    }
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
    let initialized = false;
    const initApp = () => {
        if (initialized) return;
        initialized = true;
        const app = new App();
        app.init();
    };

    if (window.pywebview) {
        initApp();
    } else {
        window.addEventListener('pywebviewready', initApp);
        // Fallback for browser preview mode
        setTimeout(initApp, 1000);
    }
});
