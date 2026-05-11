class SettingsUI {
    constructor() {
        this.i18n = {};
        this.settings = {};
        this.dirty = false;
        this.themeSwatches = {
            default:  { ok: [60,105,102], low: [185,70,60], degraded: [120,89,90], nodata: [105,105,110] },
            contrast: { ok: [0,128,128],   low: [200,50,50], degraded: [180,140,60], nodata: [80,80,90] },
            bright:   { ok: [70,150,140],  low: [220,90,80], degraded: [200,170,80], nodata: [130,130,140] },
            dark_mode:{ ok: [45,85,80],    low: [140,55,50], degraded: [90,75,60],   nodata: [60,60,65] },
            mono:     { ok: [80,80,80],    low: [80,80,80],  degraded: [80,80,80],   nodata: [80,80,80] },
        };
    }

    async init() {
        const res = await window.api.getSettings();
        if (res && res.success && res.data) {
            this.settings = res.data;
            this.platform = res.platform;
            this._populate();
        } else {
            // Browser preview mode — show defaults with clear indicator
            this._populateDefaults();
            this.platform = navigator.userAgent.toLowerCase().includes('mac') ? 'darwin' : 'win32';
            this._showBridgeWarning();
        }
        this._applyPlatformSpecificUI();
        this._bindEvents();
    }

    _applyPlatformSpecificUI() {
        if (this.platform === 'darwin') {
            const strokeRow = document.getElementById('row-icon-stroke');
            if (strokeRow) strokeRow.style.display = 'none';
        }
    }

    _populateDefaults() {
        this._setVal('api_key', '');
        this._setVal('currency', 'CNY');
        this._setVal('threshold_yuan', 1.0);
        this._setVal('alert_mode', 'always');
        this._setVal('api_alert_enabled', true);
        this._setVal('theme', 'default');
        this._setVal('icon_stroke', false);
        this._setVal('language', 'zh');
        this._setVal('interval_minutes', 10);
        this._setVal('retention_days', 30);
        this._setVal('auto_start', false);
        this._setVal('export_path', '');
        this._setVal('http_proxy', '');
        this._updateThemePreview('default');
    }

    _showBridgeWarning() {
        // Mark all inputs as disabled to indicate read-only preview mode
        const inputs = document.getElementById('settings-view').querySelectorAll('input, select, button');
        inputs.forEach(el => el.disabled = true);
        // Show a toast-like notice
        const notice = document.createElement('div');
        notice.className = 'toast error show';
        notice.textContent = '⚠ Preview mode — run via "python src/webview/main.py"';
        notice.style.position = 'static';
        notice.style.margin = '0 0 12px 0';
        notice.style.borderRadius = '8px';
        notice.style.opacity = '1';
        const scrollArea = document.querySelector('#settings-view .scroll-area');
        if (scrollArea) scrollArea.prepend(notice);
    }

    t(key) { return this.i18n[key] || key; }

    // ---- Populate ----
    _populate() {
        const s = this.settings;
        
        // Only populate API key if it's plaintext, otherwise keep it blank (masked by default)
        // If api_key_enc is set but api_key is empty (e.g. wiped for security), we just show blank.
        if (s.api_key && s.api_key !== 'masked') {
            this._setVal('api_key', s.api_key);
        } else {
            this._setVal('api_key', '');
        }

        this._setVal('currency', s.currency || 'CNY');
        this._setVal('threshold_yuan', s.threshold_yuan != null ? s.threshold_yuan : 1.0);
        this._setVal('alert_mode', s.alert_mode || 'always');
        this._setVal('api_alert_enabled', s.api_alert_enabled !== false);
        this._setVal('theme', s.theme || 'default');
        this._setVal('icon_stroke', !!s.icon_stroke);
        this._setVal('language', s.language || 'zh');
        this._setVal('interval_minutes', s.interval_minutes || 10);
        this._setVal('retention_days', s.retention_days || 30);
        this._setVal('auto_start', !!s.auto_start);
        this._setVal('export_path', s.export_path || '');
        this._setVal('http_proxy', s.http_proxy || '');

        const colors = s.icon_colors || {};
        this._setVal('color_ok', colors.ok || '');
        this._setVal('color_low', colors.low || '');
        this._setVal('color_degraded', colors.degraded || '');
        this._setVal('color_nodata', colors.nodata || '');

        this._updateThemePreview(s.theme || 'default');
        if ((s.theme || 'default') === 'custom') {
            document.getElementById('custom-colors').style.display = 'block';
        }
    }

    _setVal(id, val) {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.type === 'checkbox') el.checked = !!val;
        else el.value = val;
    }

    _getVal(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        if (el.type === 'checkbox') return el.checked;
        return el.value;
    }

    // ---- Collect ----
    _collect() {
        const cfg = {};
        cfg.api_key = this._getVal('api_key');
        cfg.currency = this._getVal('currency');
        cfg.threshold_yuan = parseFloat(this._getVal('threshold_yuan')) || 0;
        cfg.alert_mode = this._getVal('alert_mode');
        cfg.api_alert_enabled = this._getVal('api_alert_enabled');
        cfg.theme = this._getVal('theme');
        cfg.icon_stroke = this._getVal('icon_stroke');
        cfg.language = this._getVal('language');
        cfg.interval_minutes = parseInt(this._getVal('interval_minutes'), 10) || 10;
        cfg.retention_days = parseInt(this._getVal('retention_days'), 10) || 30;
        cfg.auto_start = this._getVal('auto_start');
        cfg.export_path = this._getVal('export_path');
        cfg.http_proxy = this._getVal('http_proxy');

        const existing = this.settings;
        cfg.enable_alerts = existing.enable_alerts;
        cfg.api_key_enc = existing.api_key_enc;

        const theme = cfg.theme;
        if (theme === 'custom') {
            cfg.icon_colors = {
                ok: this._getVal('color_ok'),
                low: this._getVal('color_low'),
                degraded: this._getVal('color_degraded'),
                nodata: this._getVal('color_nodata'),
            };
        } else {
            cfg.icon_colors = existing.icon_colors || {};
        }
        return cfg;
    }

    // ---- Events ----
    _bindEvents() {
        document.getElementById('theme').addEventListener('change', e => {
            const theme = e.target.value;
            this._updateThemePreview(theme);
            document.getElementById('custom-colors').style.display = theme === 'custom' ? 'block' : 'none';
            this.dirty = true;
        });

        document.getElementById('toggle_key').addEventListener('click', () => {
            const input = document.getElementById('api_key');
            const svg = document.querySelector('#toggle_key svg');
            if (input.type === 'password') {
                input.type = 'text';
                // eye-off icon
                svg.innerHTML = '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>';
            } else {
                input.type = 'password';
                // eye icon
                svg.innerHTML = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
            }
        });

        document.getElementById('browse_export').addEventListener('click', async () => {
            const path = await window.api.selectDirectory();
            if (path) {
                document.getElementById('export_path').value = path;
                this._markDirty();
            }
        });

        const fabSave = document.getElementById('fab-save');
        if (fabSave) {
            fabSave.addEventListener('click', () => this.save());
        }

        const settingsView = document.getElementById('settings-view');
        settingsView.querySelectorAll('input, select').forEach(el => {
            el.addEventListener('change', () => this._markDirty());
            if (el.tagName === 'INPUT' && el.type !== 'checkbox') {
                el.addEventListener('input', () => this._markDirty());
            }
        });

        const customColorInputs = ['color_ok', 'color_low', 'color_degraded', 'color_nodata'];
        customColorInputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('input', () => {
                    this._markDirty();
                    if (this._getVal('theme') === 'custom') {
                        this._updateThemePreview('custom');
                    }
                });
            }
        });
    }

    _markDirty() {
        this.dirty = true;
        const fab = document.getElementById('fab-save');
        if (fab) fab.classList.add('dirty');
    }

    _updateThemePreview(themeKey) {
        const container = document.getElementById('theme-preview');
        container.innerHTML = '';
        
        let colors;
        if (themeKey === 'custom') {
            const hexToRgb = (hex) => {
                const h = (hex || '').replace('#', '');
                if (h.length === 6) {
                    return [
                        parseInt(h.substring(0, 2), 16),
                        parseInt(h.substring(2, 4), 16),
                        parseInt(h.substring(4, 6), 16)
                    ];
                }
                return [128, 128, 128]; // fallback
            };
            colors = {
                ok: hexToRgb(this._getVal('color_ok')),
                low: hexToRgb(this._getVal('color_low')),
                degraded: hexToRgb(this._getVal('color_degraded')),
                nodata: hexToRgb(this._getVal('color_nodata'))
            };
        } else {
            colors = this.themeSwatches[themeKey] || this.themeSwatches.default;
        }

        const labels = ['OK', 'Low', 'Deg', '…'];
        const keys = ['ok', 'low', 'degraded', 'nodata'];
        keys.forEach((k, i) => {
            const [r, g, b] = colors[k];
            const brightness = r * 0.299 + g * 0.587 + b * 0.114;
            const textColor = brightness > 150 ? '#1c1c1c' : '#e0e0e0';
            const swatch = document.createElement('div');
            swatch.className = 'theme-swatch';
            swatch.style.background = `rgb(${r},${g},${b})`;
            swatch.style.color = textColor;
            swatch.textContent = labels[i];
            container.appendChild(swatch);
        });
    }

    async save() {
        const data = this._collect();
        // If the API key is blank but we already have an encrypted one, it means user didn't change it.
        // We only warn if there's no encrypted key either.
        if (!data.api_key.trim() && !this.settings.api_key_enc) {
            this._showToast(this.t('warn_no_key') || 'API Key cannot be empty!', 'error');
            return;
        }
        const res = await window.api.saveSettings(data);
        if (res && res.success) {
            this._showToast('✓ ' + (this.t('save') || 'Saved'), 'success');
            this.dirty = false;
            const fab = document.getElementById('fab-save');
            if (fab) fab.classList.remove('dirty');
            
            // Dynamically reload translations if language changed
            const newLang = data.language || 'zh';
            if (this.app) {
                this.app.updateI18n(newLang);
            }
            
        } else {
            this._showToast((res && res.error) || 'Save failed', 'error');
        }
    }



    _showToast(msg, type) {
        let toast = document.querySelector('.toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.className = 'toast ' + type + ' show';
        setTimeout(() => toast.classList.remove('show'), 2500);
    }
}
