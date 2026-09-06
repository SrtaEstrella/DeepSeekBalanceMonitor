#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

#[cfg(windows)]
mod windows_app {
    use chrono::{DateTime, Duration as ChronoDuration, Local, NaiveDateTime};
    use image::{DynamicImage, ImageFormat, Rgba, RgbaImage};
    use imageproc::drawing::draw_text_mut;
    use native_windows_gui as nwg;
    use reqwest::{Proxy, StatusCode};
    use rusqlite::{params, Connection, Error as SqlError};
    use rusttype::{point, Font, Scale};
    use serde::{Deserialize, Serialize};
    use std::cell::RefCell;
    use std::collections::BTreeMap;
    use std::ffi::{c_void, OsStr, OsString};
    use std::fs::{self, File, OpenOptions};
    use std::io::{Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use std::path::{Path, PathBuf};
    use std::process::Command;
    use std::ptr;
    use std::rc::Rc;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::mpsc::{self, Receiver, Sender};
    use std::sync::{Arc, Mutex, OnceLock};
    use std::thread;
    use std::time::Duration;

    mod demo;

    const APP_NAME: &str = "DeepSeek Balance Monitor";
    const TOP_UP_URL: &str = "https://platform.deepseek.com/top_up";
    const RAINMETER_ADDR: &str = "127.0.0.1:17654";
    const STARTUP_LINK_NAME: &str = "DeepSeek Balance Monitor.lnk";
    const API_KEY_PLACEHOLDER: &str = "Stored securely. Leave blank to keep the existing API key.";
    const OPENCODE_GO_API_URL: &str = "https://opencode.ai/zen/go/v1/usage";
    const OPENCODE_GO_API_KEY: &str = "opencode_go_api_key";
    const COMMAND_CODE_API_BASE: &str = "https://api.commandcode.ai/";
    const COMMAND_CODE_API_KEY: &str = "command_code_api_key";
    const GOAT_MONTHLY_CREDITS: f64 = 70.0;
    const CSIDL_STARTUP: i32 = 0x0007;
    const CSIDL_FLAG_CREATE: i32 = 0x8000;
    const COINIT_APARTMENTTHREADED: u32 = 0x2;
    const CLSCTX_INPROC_SERVER: u32 = 0x1;
    const RPC_E_CHANGED_MODE: i32 = 0x80010106u32 as i32;
    const ERROR_ALREADY_EXISTS: u32 = 183;
    const SINGLE_INSTANCE_MUTEX: &str = "Local\\DeepSeekBalanceMonitor.SingleInstance";
    const HISTORY_DEDUP_SECONDS: i64 = 120;
    const CLSID_SHELL_LINK: Guid = Guid {
        data1: 0x00021401,
        data2: 0x0000,
        data3: 0x0000,
        data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
    };
    const IID_ISHELL_LINK_W: Guid = Guid {
        data1: 0x000214F9,
        data2: 0x0000,
        data3: 0x0000,
        data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
    };
    const IID_IPERSIST_FILE: Guid = Guid {
        data1: 0x0000010B,
        data2: 0x0000,
        data3: 0x0000,
        data4: [0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46],
    };
    static DATABASE_RECREATED_WARNING: AtomicBool = AtomicBool::new(false);

    #[repr(C)]
    struct Guid {
        data1: u32,
        data2: u16,
        data3: u16,
        data4: [u8; 8],
    }

    #[repr(C)]
    struct DataBlob {
        cb_data: u32,
        pb_data: *mut u8,
    }

    #[repr(C)]
    struct IShellLinkW {
        lp_vtbl: *const IShellLinkWVtbl,
    }

    #[repr(C)]
    struct IShellLinkWVtbl {
        query_interface:
            unsafe extern "system" fn(*mut IShellLinkW, *const Guid, *mut *mut c_void) -> i32,
        add_ref: unsafe extern "system" fn(*mut IShellLinkW) -> u32,
        release: unsafe extern "system" fn(*mut IShellLinkW) -> u32,
        get_path:
            unsafe extern "system" fn(*mut IShellLinkW, *mut u16, i32, *mut c_void, u32) -> i32,
        get_id_list: unsafe extern "system" fn(*mut IShellLinkW, *mut *mut c_void) -> i32,
        set_id_list: unsafe extern "system" fn(*mut IShellLinkW, *mut c_void) -> i32,
        get_description: unsafe extern "system" fn(*mut IShellLinkW, *mut u16, i32) -> i32,
        set_description: unsafe extern "system" fn(*mut IShellLinkW, *const u16) -> i32,
        get_working_directory: unsafe extern "system" fn(*mut IShellLinkW, *mut u16, i32) -> i32,
        set_working_directory: unsafe extern "system" fn(*mut IShellLinkW, *const u16) -> i32,
        get_arguments: unsafe extern "system" fn(*mut IShellLinkW, *mut u16, i32) -> i32,
        set_arguments: unsafe extern "system" fn(*mut IShellLinkW, *const u16) -> i32,
        get_hotkey: unsafe extern "system" fn(*mut IShellLinkW, *mut u16) -> i32,
        set_hotkey: unsafe extern "system" fn(*mut IShellLinkW, u16) -> i32,
        get_show_cmd: unsafe extern "system" fn(*mut IShellLinkW, *mut i32) -> i32,
        set_show_cmd: unsafe extern "system" fn(*mut IShellLinkW, i32) -> i32,
        get_icon_location:
            unsafe extern "system" fn(*mut IShellLinkW, *mut u16, i32, *mut i32) -> i32,
        set_icon_location: unsafe extern "system" fn(*mut IShellLinkW, *const u16, i32) -> i32,
        set_relative_path: unsafe extern "system" fn(*mut IShellLinkW, *const u16, u32) -> i32,
        resolve: unsafe extern "system" fn(*mut IShellLinkW, *mut c_void, u32) -> i32,
        set_path: unsafe extern "system" fn(*mut IShellLinkW, *const u16) -> i32,
    }

    #[repr(C)]
    struct IPersistFile {
        lp_vtbl: *const IPersistFileVtbl,
    }

    #[repr(C)]
    struct IPersistFileVtbl {
        query_interface:
            unsafe extern "system" fn(*mut IPersistFile, *const Guid, *mut *mut c_void) -> i32,
        add_ref: unsafe extern "system" fn(*mut IPersistFile) -> u32,
        release: unsafe extern "system" fn(*mut IPersistFile) -> u32,
        get_class_id: unsafe extern "system" fn(*mut IPersistFile, *mut Guid) -> i32,
        is_dirty: unsafe extern "system" fn(*mut IPersistFile) -> i32,
        load: unsafe extern "system" fn(*mut IPersistFile, *const u16, u32) -> i32,
        save: unsafe extern "system" fn(*mut IPersistFile, *const u16, i32) -> i32,
        save_completed: unsafe extern "system" fn(*mut IPersistFile, *const u16) -> i32,
        get_cur_file: unsafe extern "system" fn(*mut IPersistFile, *mut *mut u16) -> i32,
    }

    struct ComApartment {
        uninitialize: bool,
    }

    impl Drop for ComApartment {
        fn drop(&mut self) {
            if self.uninitialize {
                // SAFETY: This balances a successful CoInitializeEx call in init_com.
                unsafe { CoUninitialize() };
            }
        }
    }

    struct ShellLinkPtr(*mut IShellLinkW);

    impl Drop for ShellLinkPtr {
        fn drop(&mut self) {
            // SAFETY: The pointer owns one COM reference returned by CoCreateInstance.
            unsafe { ((*(*self.0).lp_vtbl).release)(self.0) };
        }
    }

    struct PersistFilePtr(*mut IPersistFile);

    impl Drop for PersistFilePtr {
        fn drop(&mut self) {
            // SAFETY: The pointer owns one COM reference returned by QueryInterface.
            unsafe { ((*(*self.0).lp_vtbl).release)(self.0) };
        }
    }

    #[link(name = "ole32")]
    extern "system" {
        fn CoInitializeEx(reserved: *mut c_void, coinit: u32) -> i32;
        fn CoUninitialize();
        fn CoCreateInstance(
            class_id: *const Guid,
            outer: *mut c_void,
            context: u32,
            interface_id: *const Guid,
            instance: *mut *mut c_void,
        ) -> i32;
    }

    #[link(name = "shell32")]
    extern "system" {
        fn SHGetFolderPathW(
            hwnd: *mut c_void,
            csidl: i32,
            token: *mut c_void,
            flags: u32,
            path: *mut u16,
        ) -> i32;
    }

    #[link(name = "crypt32")]
    extern "system" {
        fn CryptProtectData(
            data_in: *mut DataBlob,
            data_descr: *const u16,
            optional_entropy: *mut DataBlob,
            reserved: *mut c_void,
            prompt_struct: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;
        fn CryptUnprotectData(
            data_in: *mut DataBlob,
            data_descr: *mut *mut u16,
            optional_entropy: *mut DataBlob,
            reserved: *mut c_void,
            prompt_struct: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(mem: *mut c_void) -> *mut c_void;
        fn CreateMutexW(
            attributes: *mut c_void,
            initial_owner: i32,
            name: *const u16,
        ) -> *mut c_void;
        fn GetLastError() -> u32;
    }

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(
            hwnd: *mut c_void,
            text: *const u16,
            caption: *const u16,
            message_type: u32,
        ) -> i32;
    }

    #[derive(Clone, Serialize, Deserialize)]
    struct AppConfig {
        #[serde(default)]
        api_key: String,
        #[serde(default = "default_interval")]
        interval_minutes: u64,
        #[serde(default = "default_threshold")]
        threshold_yuan: f64,
        #[serde(default = "default_lang")]
        language: String,
        #[serde(default = "default_ui_lang")]
        ui_language: String,
        #[serde(default = "default_auto_start")]
        auto_start: bool,
        #[serde(default = "default_alert_mode")]
        alert_mode: String,
        #[serde(default = "default_api_alert_enabled")]
        api_alert_enabled: bool,
        #[serde(default = "default_retention_days")]
        retention_days: u64,
        #[serde(default)]
        export_path: String,
        #[serde(default)]
        http_proxy: String,
        #[serde(default)]
        proxy_enabled: bool,
        #[serde(default = "default_theme")]
        theme: String,
        #[serde(default)]
        icon_colors: BTreeMap<String, String>,
        #[serde(default)]
        icon_stroke: bool,
        #[serde(flatten)]
        extra: BTreeMap<String, serde_json::Value>,
    }

    impl Default for AppConfig {
        fn default() -> Self {
            Self {
                api_key: String::new(),
                interval_minutes: default_interval(),
                threshold_yuan: default_threshold(),
                language: default_lang(),
                ui_language: default_ui_lang(),
                auto_start: default_auto_start(),
                alert_mode: default_alert_mode(),
                api_alert_enabled: default_api_alert_enabled(),
                retention_days: default_retention_days(),
                export_path: String::new(),
                http_proxy: String::new(),
                proxy_enabled: false,
                theme: default_theme(),
                icon_colors: BTreeMap::new(),
                icon_stroke: false,
                extra: BTreeMap::new(),
            }
        }
    }

    fn default_interval() -> u64 {
        10
    }

    fn default_threshold() -> f64 {
        1.0
    }

    fn default_auto_start() -> bool {
        false
    }

    fn default_lang() -> String {
        "en".to_string()
    }

    fn default_ui_lang() -> String {
        "zh".to_string()
    }

    fn default_api_alert_enabled() -> bool {
        true
    }

    fn default_alert_mode() -> String {
        "once".to_string()
    }

    fn default_retention_days() -> u64 {
        30
    }

    fn default_theme() -> String {
        "default".to_string()
    }

    fn custom_or_default_colors(config: &AppConfig) -> BTreeMap<String, String> {
        let mut colors = BTreeMap::new();
        for (key, value) in [
            ("ok", "3c6966"),
            ("low", "b9463c"),
            ("degraded", "78695a"),
            ("nodata", "69696e"),
        ] {
            colors.insert(
                key.to_string(),
                config
                    .icon_colors
                    .get(key)
                    .cloned()
                    .unwrap_or_else(|| value.to_string()),
            );
        }
        colors
    }

    fn parse_icon_colors(values: [String; 4]) -> Result<BTreeMap<String, String>, String> {
        let keys = ["ok", "low", "degraded", "nodata"];
        let mut colors = BTreeMap::new();
        for (key, value) in keys.into_iter().zip(values.into_iter()) {
            let hex = value.trim().trim_start_matches('#');
            if !is_hex_color(hex) {
                return Err(format!("{key} color must be a 6-digit hex value."));
            }
            colors.insert(key.to_string(), hex.to_string());
        }
        Ok(colors)
    }

    fn is_hex_color(value: &str) -> bool {
        value.len() == 6 && value.chars().all(|ch| ch.is_ascii_hexdigit())
    }

    #[derive(Clone, Debug)]
    struct Balance {
        total_balance: f64,
        granted_balance: f64,
        topped_up_balance: f64,
    }

    #[derive(Clone, Debug)]
    struct HistoryRecord {
        timestamp: String,
        currency: String,
        total: f64,
        topped: f64,
        granted: f64,
        service_status: String,
    }

    #[derive(Clone, Debug)]
    struct OpenCodeGoUsage {
        usage_percent: f64,
        percent_remaining: f64,
        reset_in_sec: i64,
    }

    #[derive(Clone, Debug, Default)]
    struct OpenCodeGoQuota {
        rolling: Option<OpenCodeGoUsage>,
        weekly: Option<OpenCodeGoUsage>,
        monthly: Option<OpenCodeGoUsage>,
    }

    #[derive(Deserialize)]
    struct OpenCodeGoApiResponse {
        usage: OpenCodeGoApiUsage,
    }

    #[derive(Deserialize)]
    struct OpenCodeGoApiUsage {
        #[serde(default)]
        rolling: Option<OpenCodeGoApiWindow>,
        #[serde(default)]
        weekly: Option<OpenCodeGoApiWindow>,
        #[serde(default)]
        monthly: Option<OpenCodeGoApiWindow>,
    }

    #[derive(Deserialize)]
    struct OpenCodeGoApiWindow {
        #[serde(default)]
        percent: f64,
        #[serde(rename = "resetsAt", default)]
        resets_at: Option<String>,
    }

    #[derive(Clone, Debug, Default)]
    struct CommandCodeQuota {
        five_hour: Option<CommandCodeWindow>,
        weekly: Option<CommandCodeWindow>,
        monthly: Option<CommandCodeWindow>,
    }

    #[derive(Clone, Debug)]
    struct CommandCodeWindow {
        used: f64,
        cap: f64,
        reset_in_sec: i64,
    }

    #[derive(Deserialize)]
    struct CommandCodeApiResponse {
        credits: CommandCodeApiCredits,
        #[serde(rename = "windowLimits")]
        window_limits: CommandCodeApiLimits,
    }

    #[derive(Deserialize)]
    struct CommandCodeApiCredits {
        #[serde(rename = "planId", default)]
        plan_id: Option<String>,
        #[serde(rename = "monthlyCredits", default)]
        monthly_credits: Option<f64>,
    }

    #[derive(Deserialize)]
    struct CommandCodeApiLimits {
        #[serde(rename = "fiveHour", default)]
        five_hour: Option<CommandCodeApiWindow>,
        #[serde(default)]
        weekly: Option<CommandCodeApiWindow>,
    }

    #[derive(Deserialize)]
    struct CommandCodeApiWindow {
        #[serde(default, deserialize_with = "deserialize_number")]
        used: f64,
        #[serde(default, deserialize_with = "deserialize_number")]
        cap: f64,
        #[serde(
            rename = "resetAt",
            default,
            deserialize_with = "deserialize_optional_number"
        )]
        reset_at: Option<f64>,
    }

    fn deserialize_number<'de, D>(deserializer: D) -> Result<f64, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        use serde::de::Error;
        let value = serde_json::Value::deserialize(deserializer)?;
        match value {
            serde_json::Value::Number(number) => number
                .as_f64()
                .ok_or_else(|| D::Error::custom("expected numeric value")),
            serde_json::Value::String(text) => text
                .parse::<f64>()
                .map_err(|_| D::Error::custom("expected numeric string")),
            _ => Err(D::Error::custom("expected number or numeric string")),
        }
    }

    fn deserialize_optional_number<'de, D>(deserializer: D) -> Result<Option<f64>, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        use serde::de::Error;
        let value = serde_json::Value::deserialize(deserializer)?;
        match value {
            serde_json::Value::Null => Ok(None),
            serde_json::Value::Number(number) => number
                .as_f64()
                .ok_or_else(|| D::Error::custom("expected numeric value"))
                .map(Some),
            serde_json::Value::String(text) => text
                .parse::<f64>()
                .map(Some)
                .map_err(|_| D::Error::custom("expected numeric string")),
            _ => Err(D::Error::custom("expected number or numeric string")),
        }
    }

    #[derive(Deserialize)]
    struct CommandCodeApiWhoami {
        org: Option<CommandCodeApiOrg>,
    }

    #[derive(Deserialize)]
    struct CommandCodeApiOrg {
        #[serde(default)]
        id: Option<String>,
    }

    struct HistorySummary {
        currency: String,
        records: usize,
        first_time: String,
        last_time: String,
        latest_total: f64,
        latest_topped: f64,
        latest_granted: f64,
        min_total: f64,
        max_total: f64,
        avg_total: f64,
        change_total: f64,
    }

    #[derive(Clone, Debug)]
    struct ConsumptionRate {
        hourly_rate: f64,
        busy_hours_left: f64,
        currency: String,
    }

    #[derive(Default)]
    struct RuntimeState {
        config: AppConfig,
        balances: BTreeMap<String, Balance>,
        last_check: Option<DateTime<Local>>,
        error: Option<String>,
        checking: bool,
        alert_suppressed: bool,
        service_status: String,
        service_status_checked: bool,
        opencode_configured: bool,
        opencode: Option<OpenCodeGoQuota>,
        opencode_error: Option<String>,
        command_code_configured: bool,
        command_code: Option<CommandCodeQuota>,
        command_code_error: Option<String>,
    }

    struct CheckResult {
        balance: Result<BTreeMap<String, Balance>, String>,
        service_status: String,
        demo_mode: bool,
    }

    enum UiMessage {
        CheckFinished(CheckResult),
    }

    #[derive(Deserialize)]
    struct ApiResponse {
        #[allow(dead_code)]
        #[serde(default)]
        is_available: bool,
        #[serde(default)]
        balance_infos: Vec<ApiBalanceInfo>,
    }

    #[derive(Deserialize)]
    struct ApiBalanceInfo {
        #[serde(default = "default_currency")]
        currency: String,
        #[serde(default)]
        total_balance: String,
        #[serde(default)]
        granted_balance: String,
        #[serde(default)]
        topped_up_balance: String,
    }

    fn default_currency() -> String {
        "CNY".to_string()
    }

    pub fn run() -> Result<(), String> {
        if let Err(error) = acquire_single_instance_lock() {
            log_line(&error);
            show_already_running_message();
            return Err(error);
        }
        nwg::init().map_err(|e| e.to_string())?;
        set_ui_font();
        let ui = AppUi::build().map_err(|e| e.to_string())?;
        if let Err(error) = prune_logs_on_startup(&ui.state.lock().unwrap().config) {
            log_line(&format!("Log retention cleanup failed: {error}"));
        }
        if let Err(error) = prune_balance_history(ui.state.lock().unwrap().config.retention_days) {
            log_line(&format!("Balance history cleanup failed: {error}"));
        }
        log_line("Rust Windows app started");
        ui.sync_auto_start();

        if DATABASE_RECREATED_WARNING.swap(false, Ordering::SeqCst) {
            ui.notify_database_recreated();
        }
        if ui.state.lock().unwrap().config.api_key.trim().is_empty() {
            ui.show_settings();
            ui.notify_missing_api_key();
        }

        ui.start_check();
        spawn_opencode_refresh(ui.state.clone());
        spawn_command_code_refresh(ui.state.clone());
        nwg::dispatch_thread_events();
        log_line("Rust Windows app exited");
        Ok(())
    }

    fn set_ui_font() {
        let mut font = nwg::Font::default();
        if nwg::Font::builder()
            .family(ui_font_family())
            .size_absolute(12)
            .build(&mut font)
            .is_ok()
        {
            let _ = nwg::Font::set_global_default(Some(font));
        }
    }

    /// UI 统一使用雅黑，系统缺失时回落宋体。CreateFontW 对不存在的字体名会静默替换，
    /// 因此用字体枚举做真实存在性检测，不能依赖 set_global_family 的返回值。
    fn ui_font_family() -> &'static str {
        static FAMILY: OnceLock<&'static str> = OnceLock::new();
        *FAMILY.get_or_init(|| {
            // 组内是同一字体的别名，组间按优先级回落
            const CANDIDATES: [&[&str]; 3] = [
                &["Microsoft YaHei UI"],
                &["Microsoft YaHei", "微软雅黑"],
                &["SimSun", "宋体"],
            ];
            let installed = nwg::Font::families();
            for aliases in CANDIDATES {
                if aliases
                    .iter()
                    .any(|name| installed.iter().any(|f| f.as_str() == *name))
                {
                    return aliases[0];
                }
            }
            "SimSun"
        })
    }

    struct AppUi {
        window: nwg::MessageWindow,
        tray: nwg::TrayNotification,
        tray_menu: nwg::Menu,
        view_item: nwg::MenuItem,
        check_item: nwg::MenuItem,
        top_up_item: nwg::MenuItem,
        auto_start_item: nwg::MenuItem,
        settings_item: nwg::MenuItem,
        quit_item: nwg::MenuItem,
        notice: nwg::Notice,
        timer: nwg::AnimationTimer,
        icon: RefCell<nwg::Icon>,
        icon_path: PathBuf,
        state: Arc<Mutex<RuntimeState>>,
        tx: Sender<UiMessage>,
        rx: RefCell<Receiver<UiMessage>>,
        handlers: RefCell<Vec<nwg::EventHandler>>,
        settings: RefCell<Option<Rc<SettingsWindow>>>,
    }

    impl AppUi {
        fn build() -> Result<Rc<Self>, nwg::NwgError> {
            let config = load_config();
            let state = Arc::new(Mutex::new(RuntimeState {
                config: config.clone(),
                ..RuntimeState::default()
            }));
            let icon_path = config_dir().join("tray.ico");
            let _ = write_tray_icon(&icon_path, "...", false, false, &config);

            let mut window = Default::default();
            let mut icon = Default::default();
            let mut tray = Default::default();
            let mut tray_menu = Default::default();
            let mut view_item = Default::default();
            let mut check_item = Default::default();
            let mut top_up_item = Default::default();
            let mut auto_start_item = Default::default();
            let mut settings_item = Default::default();
            let mut quit_item = Default::default();
            let mut notice = Default::default();
            let mut timer = Default::default();

            nwg::MessageWindow::builder().build(&mut window)?;
            nwg::Icon::builder()
                .source_file(Some(path_text(&icon_path).as_str()))
                .build(&mut icon)?;
            nwg::TrayNotification::builder()
                .parent(&window)
                .icon(Some(&icon))
                .tip(Some(tr(&config.ui_language, "checking")))
                .build(&mut tray)?;
            nwg::Menu::builder()
                .popup(true)
                .parent(&window)
                .build(&mut tray_menu)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "view_balance"))
                .parent(&tray_menu)
                .build(&mut view_item)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "check_now"))
                .parent(&tray_menu)
                .build(&mut check_item)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "top_up"))
                .parent(&tray_menu)
                .build(&mut top_up_item)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "auto_start"))
                .check(config.auto_start)
                .parent(&tray_menu)
                .build(&mut auto_start_item)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "settings"))
                .parent(&tray_menu)
                .build(&mut settings_item)?;
            nwg::MenuItem::builder()
                .text(tr(&config.ui_language, "quit"))
                .parent(&tray_menu)
                .build(&mut quit_item)?;
            nwg::Notice::builder().parent(&window).build(&mut notice)?;
            nwg::AnimationTimer::builder()
                .parent(&window)
                .interval(Duration::from_secs(config.interval_minutes.max(1) * 60))
                .build(&mut timer)?;

            let (tx, rx) = mpsc::channel();
            let ui = Rc::new(Self {
                window,
                tray,
                tray_menu,
                view_item,
                check_item,
                top_up_item,
                auto_start_item,
                settings_item,
                quit_item,
                notice,
                timer,
                icon: RefCell::new(icon),
                icon_path,
                state,
                tx,
                rx: RefCell::new(rx),
                handlers: RefCell::new(Vec::new()),
                settings: RefCell::new(None),
            });

            let weak = Rc::downgrade(&ui);
            let handler =
                nwg::full_bind_event_handler(&ui.window.handle, move |evt, _data, handle| {
                    if let Some(ui) = weak.upgrade() {
                        ui.handle_event(evt, handle);
                    }
                });
            ui.handlers.borrow_mut().push(handler);
            start_rainmeter_server(ui.state.clone(), ui.tx.clone(), ui.notice.sender());
            ui.timer.start();
            Ok(ui)
        }

        fn handle_event(self: &Rc<Self>, evt: nwg::Event, handle: nwg::ControlHandle) {
            match evt {
                nwg::Event::OnContextMenu if &handle == &self.tray => self.show_menu(),
                nwg::Event::OnMousePress(nwg::MousePressEvent::MousePressLeftUp)
                    if &handle == &self.tray =>
                {
                    self.show_balance()
                }
                nwg::Event::OnMenuItemSelected if &handle == &self.view_item => self.show_balance(),
                nwg::Event::OnMenuItemSelected if &handle == &self.check_item => self.start_check(),
                nwg::Event::OnMenuItemSelected if &handle == &self.top_up_item => {
                    self.open_top_up()
                }
                nwg::Event::OnMenuItemSelected if &handle == &self.auto_start_item => {
                    self.toggle_auto_start()
                }
                nwg::Event::OnMenuItemSelected if &handle == &self.settings_item => {
                    self.show_settings()
                }
                nwg::Event::OnMenuItemSelected if &handle == &self.quit_item => self.quit(),
                nwg::Event::OnNotice if &handle == &self.notice => self.process_messages(),
                nwg::Event::OnTimerTick if &handle == &self.timer => self.start_check(),
                _ => {}
            }
        }

        fn show_menu(&self) {
            let (x, y) = nwg::GlobalCursor::position();
            self.tray_menu.popup(x, y);
        }

        fn notify_missing_api_key(&self) {
            let (title, message) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                (
                    tr(lang, "api_key_missing_title").to_string(),
                    tr(lang, "api_key_missing_body").to_string(),
                )
            };
            self.tray.show(&message, Some(&title), None, None);
        }

        fn notify_database_recreated(&self) {
            let (title, message) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                (
                    tr(lang, "database_recreated_title").to_string(),
                    tr(lang, "database_recreated_body").to_string(),
                )
            };
            self.tray.show(&message, Some(&title), None, None);
        }

        fn sync_auto_start(&self) {
            let enabled = self.state.lock().unwrap().config.auto_start;
            self.auto_start_item.set_checked(enabled);
            if let Err(error) = set_auto_start(enabled) {
                log_line(&format!("Auto-start update failed: {error}"));
            }
        }

        fn toggle_auto_start(&self) {
            let mut config = self.state.lock().unwrap().config.clone();
            config.auto_start = !config.auto_start;
            if let Err(error) = save_config(&config) {
                log_line(&format!("Config save failed: {error}"));
            }
            if let Err(error) = set_auto_start(config.auto_start) {
                log_line(&format!("Auto-start update failed: {error}"));
            }
            self.auto_start_item.set_checked(config.auto_start);
            if let Some(settings) = self.settings.borrow().as_ref() {
                settings.auto_start.set_check_state(if config.auto_start {
                    nwg::CheckBoxState::Checked
                } else {
                    nwg::CheckBoxState::Unchecked
                });
            }
            self.state.lock().unwrap().config = config;
        }

        fn start_check(&self) {
            let config = {
                let mut state = self.state.lock().unwrap();
                if state.checking {
                    return;
                }
                state.checking = true;
                state.error = None;
                state.config.clone()
            };
            self.update_tray();

            spawn_balance_check(config, self.tx.clone(), self.notice.sender());
        }

        fn process_messages(&self) {
            while let Ok(message) = self.rx.borrow_mut().try_recv() {
                match message {
                    UiMessage::CheckFinished(result) => {
                        let mut should_notify = false;
                        let mut should_notify_api = None;
                        {
                            let mut state = self.state.lock().unwrap();
                            let demo_mode = result.demo_mode;
                            state.checking = false;
                            let previous_service_status = state.service_status.clone();
                            let api_changed = state.service_status_checked
                                && previous_service_status != result.service_status;
                            if !demo_mode
                                && api_changed
                                && state.config.api_alert_enabled
                                && previous_service_status != "unknown"
                                && result.service_status != "unknown"
                            {
                                should_notify_api = Some(service_degraded(&result.service_status));
                            }
                            state.service_status = result.service_status;
                            state.service_status_checked = true;
                            match result.balance {
                                Ok(balances) => {
                                    state.balances = balances;
                                    state.last_check = Some(Local::now());
                                    state.error = None;
                                    if demo_mode {
                                        log_line("Demo balance check succeeded");
                                    } else {
                                        let low_balance = is_low_balance(&state);
                                        should_notify =
                                            should_low_balance_alert(&mut state, low_balance);
                                        log_line("Balance check succeeded");
                                    }
                                }
                                Err(error) => {
                                    if service_degraded(&state.service_status)
                                        && !state.balances.is_empty()
                                    {
                                        state.error = None;
                                    } else {
                                        state.balances.clear();
                                        state.error = Some(error.clone());
                                    }
                                    log_line(&format!("Balance check failed: {error}"));
                                }
                            }
                        }
                        self.update_tray();
                        if should_notify {
                            self.notify_low_balance();
                        }
                        if let Some(degraded) = should_notify_api {
                            self.notify_api_status_change(degraded);
                        }
                    }
                }
            }
        }

        fn update_tray(&self) {
            let (tooltip, label, low_balance, service_degraded) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                if state.checking {
                    (
                        tr(lang, "checking").to_string(),
                        "...".to_string(),
                        false,
                        false,
                    )
                } else if let Some(error) = &state.error {
                    (
                        format!("{}: {}", tr(lang, "error"), error),
                        "!".to_string(),
                        false,
                        false,
                    )
                } else if let Some((currency, balance)) = preferred_balance(&state.balances) {
                    (
                        format!(
                            "{}: {} {}",
                            tr(lang, "total_balance"),
                            format_amount(balance.total_balance),
                            currency
                        ),
                        icon_label(balance.total_balance),
                        is_low_balance(&state),
                        service_degraded(&state.service_status),
                    )
                } else {
                    (
                        tr(lang, "checking").to_string(),
                        "...".to_string(),
                        false,
                        false,
                    )
                }
            };

            self.tray.set_tip(&tooltip);
            let icon_result = {
                let state = self.state.lock().unwrap();
                write_tray_icon(
                    &self.icon_path,
                    &label,
                    low_balance,
                    service_degraded,
                    &state.config,
                )
            };
            if let Err(error) = icon_result {
                log_line(&format!("Icon update failed: {error}"));
                return;
            }

            let mut icon = Default::default();
            if nwg::Icon::builder()
                .source_file(Some(path_text(&self.icon_path).as_str()))
                .build(&mut icon)
                .is_ok()
            {
                self.tray.set_icon(&icon);
                *self.icon.borrow_mut() = icon;
            }
        }

        fn show_balance(&self) {
            let (title, message) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                let rate = if demo::is_enabled(&state.config.api_key) {
                    open_history_db()
                        .and_then(|conn| {
                            demo::prepare(&conn)?;
                            demo::consumption_rate(&conn)
                        })
                        .ok()
                } else {
                    consumption_rate_with_fallback(
                        state.config.retention_days,
                        state.config.interval_minutes,
                    )
                    .ok()
                    .flatten()
                };
                let message = balance_notification_message(
                    lang,
                    &state.balances,
                    rate.as_ref(),
                    state.error.as_deref(),
                    state.last_check,
                    &state.service_status,
                    Local::now(),
                );
                (tr(lang, "bal_title").to_string(), message)
            };
            self.tray.show(&message, Some(&title), None, None);
        }

        fn open_top_up(&self) {
            if let Err(error) = open_url(TOP_UP_URL) {
                log_line(&format!("Failed to open top-up URL: {error}"));
            }
        }

        fn notify_low_balance(&self) {
            let (enabled, title, message) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                if let Some((code, balance)) = preferred_balance(&state.balances) {
                    (
                        true,
                        tr(lang, "low_balance_title").to_string(),
                        format!(
                            "{} {} {}, {} {} {}",
                            tr(lang, "low_balance_body"),
                            format_amount(balance.total_balance),
                            code,
                            tr(lang, "threshold"),
                            format_amount(state.config.threshold_yuan),
                            code
                        ),
                    )
                } else {
                    (false, String::new(), String::new())
                }
            };
            if enabled {
                self.tray.show(&message, Some(&title), None, None);
            }
        }

        fn notify_api_status_change(&self, degraded: bool) {
            let (title, message) = {
                let state = self.state.lock().unwrap();
                let lang = state.config.ui_language.as_str();
                if degraded {
                    (
                        tr(lang, "api_degraded_title").to_string(),
                        format!(
                            "{}{}",
                            tr(lang, "api_degraded_msg"),
                            service_status_text(lang, &state.service_status)
                        ),
                    )
                } else {
                    (
                        tr(lang, "api_recovered_title").to_string(),
                        tr(lang, "api_recovered_msg").to_string(),
                    )
                }
            };
            self.tray.show(&message, Some(&title), None, None);
        }

        fn show_settings(self: &Rc<Self>) {
            if let Some(settings) = self.settings.borrow().as_ref() {
                settings.window.set_visible(true);
                settings.window.set_focus();
                return;
            }

            match SettingsWindow::build(self.clone()) {
                Ok(settings) => {
                    settings.window.set_visible(true);
                    settings.api_input.set_focus();
                    self.settings.borrow_mut().replace(settings);
                }
                Err(error) => log_line(&format!("Settings build failed: {error}")),
            }
        }

        fn settings_closed(&self) {
            self.settings.borrow_mut().take();
        }

        fn apply_config(&self, config: AppConfig) {
            if let Err(error) = save_config(&config) {
                log_line(&format!("Config save failed: {error}"));
            }
            if let Err(error) = set_auto_start(config.auto_start) {
                log_line(&format!("Auto-start update failed: {error}"));
            }
            self.auto_start_item.set_checked(config.auto_start);
            {
                let mut state = self.state.lock().unwrap();
                if state.config.alert_mode != config.alert_mode {
                    state.alert_suppressed = false;
                }
                state.config = config.clone();
            }
            self.timer
                .set_interval(Duration::from_secs(config.interval_minutes.max(1) * 60));
            self.timer.start();
            self.start_check();
        }

        fn quit(&self) {
            self.tray.set_visibility(false);
            nwg::stop_thread_dispatch();
        }
    }

    impl Drop for AppUi {
        fn drop(&mut self) {
            for handler in self.handlers.borrow_mut().drain(..) {
                nwg::unbind_event_handler(&handler);
            }
        }
    }

    #[derive(Clone)]
    struct RainmeterSnapshot {
        config: AppConfig,
        balances: BTreeMap<String, Balance>,
        last_check: Option<DateTime<Local>>,
        error: Option<String>,
        checking: bool,
        service_status: String,
        opencode_configured: bool,
        opencode: Option<OpenCodeGoQuota>,
        opencode_error: Option<String>,
        command_code_configured: bool,
        command_code: Option<CommandCodeQuota>,
        command_code_error: Option<String>,
    }

    fn spawn_opencode_refresh(state: Arc<Mutex<RuntimeState>>) {
        thread::spawn(move || loop {
            let api_key = read_secure_value(OPENCODE_GO_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            let configured = !api_key.is_empty();
            let config = state.lock().unwrap().config.clone();
            let result = if configured {
                fetch_opencode_go_quota(&api_key, effective_http_proxy(&config)).map(Some)
            } else {
                Ok(None)
            };
            {
                let mut state = state.lock().unwrap();
                state.opencode_configured = configured;
                match result {
                    Ok(Some(quota)) => {
                        state.opencode = Some(quota);
                        state.opencode_error = None;
                    }
                    Ok(None) => {
                        state.opencode = None;
                        state.opencode_error = None;
                    }
                    Err(error) => {
                        state.opencode_error = Some(error);
                    }
                }
            }
            thread::sleep(Duration::from_secs(600));
        });
    }

    fn spawn_command_code_refresh(state: Arc<Mutex<RuntimeState>>) {
        thread::spawn(move || loop {
            let api_key = read_secure_value(COMMAND_CODE_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            let configured = !api_key.is_empty();
            let config = state.lock().unwrap().config.clone();
            let result = if configured {
                fetch_command_code_quota(&api_key, effective_http_proxy(&config)).map(Some)
            } else {
                Ok(None)
            };
            {
                let mut state = state.lock().unwrap();
                state.command_code_configured = configured;
                match result {
                    Ok(Some(quota)) => {
                        state.command_code = Some(quota);
                        state.command_code_error = None;
                    }
                    Ok(None) => {
                        state.command_code = None;
                        state.command_code_error = None;
                    }
                    Err(error) => {
                        state.command_code_error = Some(error);
                    }
                }
            }
            thread::sleep(Duration::from_secs(600));
        });
    }

    fn spawn_balance_check(config: AppConfig, tx: Sender<UiMessage>, notice: nwg::NoticeSender) {
        thread::spawn(move || {
            let demo_mode = demo::is_enabled(&config.api_key);
            let service_status = if demo_mode {
                "none".to_string()
            } else {
                fetch_service_status(effective_http_proxy(&config))
            };
            let balance = if config.api_key.trim().is_empty() {
                Err("No API Key configured".to_string())
            } else if demo_mode {
                open_history_db().and_then(|conn| {
                    demo::prepare(&conn)?;
                    demo::balances(&conn)
                })
            } else {
                fetch_balance(&config.api_key, effective_http_proxy(&config))
            };
            if !demo_mode {
                if let Ok(balances) = &balance {
                    if let Err(error) = save_balance_history(balances, &service_status) {
                        log_line(&format!("Failed to save balance history: {error}"));
                    }
                }
            }
            let _ = tx.send(UiMessage::CheckFinished(CheckResult {
                balance,
                service_status,
                demo_mode,
            }));
            notice.notice();
        });
    }

    fn start_rainmeter_server(
        state: Arc<Mutex<RuntimeState>>,
        tx: Sender<UiMessage>,
        notice: nwg::NoticeSender,
    ) {
        thread::spawn(move || {
            let listener = match TcpListener::bind(RAINMETER_ADDR) {
                Ok(listener) => listener,
                Err(error) => {
                    log_line(&format!("Rainmeter server bind failed: {error}"));
                    return;
                }
            };
            log_line(&format!("Rainmeter server listening on {RAINMETER_ADDR}"));
            for stream in listener.incoming() {
                match stream {
                    Ok(stream) => handle_rainmeter_request(stream, &state, &tx, notice),
                    Err(error) => log_line(&format!("Rainmeter request failed: {error}")),
                }
            }
        });
    }

    fn handle_rainmeter_request(
        mut stream: TcpStream,
        state: &Arc<Mutex<RuntimeState>>,
        tx: &Sender<UiMessage>,
        notice: nwg::NoticeSender,
    ) {
        let mut buffer = [0u8; 2048];
        let read = match stream.read(&mut buffer) {
            Ok(read) => read,
            Err(error) => {
                log_line(&format!("Rainmeter request read failed: {error}"));
                return;
            }
        };
        let request = String::from_utf8_lossy(&buffer[..read]);
        let target = request
            .lines()
            .next()
            .and_then(|line| line.split_whitespace().nth(1))
            .unwrap_or("/");
        if target.starts_with("/check") {
            trigger_rainmeter_check(state, tx, notice);
        }
        let (status, body) = if target.starts_with("/widget-status") || target.starts_with("/check")
        {
            ("200 OK", rainmeter_status_body(state, target))
        } else {
            ("404 Not Found", "{\"error\":\"not found\"}".to_string())
        };
        write_http_response(
            &mut stream,
            status,
            "application/json; charset=utf-8",
            &body,
        );
    }

    fn trigger_rainmeter_check(
        state: &Arc<Mutex<RuntimeState>>,
        tx: &Sender<UiMessage>,
        notice: nwg::NoticeSender,
    ) {
        let config = {
            let mut state = state.lock().unwrap();
            if state.checking {
                return;
            }
            state.checking = true;
            state.error = None;
            state.config.clone()
        };
        spawn_balance_check(config, tx.clone(), notice);
    }

    fn rainmeter_status_body(state: &Arc<Mutex<RuntimeState>>, target: &str) -> String {
        let snapshot = {
            let state = state.lock().unwrap();
            RainmeterSnapshot {
                config: state.config.clone(),
                balances: state.balances.clone(),
                last_check: state.last_check,
                error: state.error.clone(),
                checking: state.checking,
                service_status: state.service_status.clone(),
                opencode_configured: state.opencode_configured,
                opencode: state.opencode.clone(),
                opencode_error: state.opencode_error.clone(),
                command_code_configured: state.command_code_configured,
                command_code: state.command_code.clone(),
                command_code_error: state.command_code_error.clone(),
            }
        };
        let lang = request_language(target, &snapshot.config.ui_language);
        let rate = current_consumption_rate(&snapshot.config);
        rainmeter_status_json(&snapshot, rate.as_ref(), &lang, Local::now())
    }

    fn write_http_response(stream: &mut TcpStream, status: &str, content_type: &str, body: &str) {
        let response = format!(
            "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nCache-Control: no-store\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.as_bytes().len()
        );
        if let Err(error) = stream.write_all(response.as_bytes()) {
            log_line(&format!("Rainmeter response write failed: {error}"));
        }
    }

    fn request_language(target: &str, fallback: &str) -> String {
        if target.contains("lang=en") {
            "en".to_string()
        } else if target.contains("lang=zh") {
            "zh".to_string()
        } else if fallback == "en" {
            "en".to_string()
        } else {
            "zh".to_string()
        }
    }

    fn current_consumption_rate(config: &AppConfig) -> Option<ConsumptionRate> {
        if demo::is_enabled(&config.api_key) {
            open_history_db()
                .and_then(|conn| {
                    demo::prepare(&conn)?;
                    demo::consumption_rate(&conn)
                })
                .ok()
        } else {
            consumption_rate_with_fallback(config.retention_days, config.interval_minutes)
                .ok()
                .flatten()
        }
    }

    fn rainmeter_status_json(
        snapshot: &RainmeterSnapshot,
        rate: Option<&ConsumptionRate>,
        lang: &str,
        now: DateTime<Local>,
    ) -> String {
        let (balance_line, status_line) =
            if let Some((code, balance)) = preferred_balance(&snapshot.balances) {
                (
                    format!("💰 {} {}", format_amount(balance.total_balance), code),
                    format!(
                        "{}: {} {}",
                        tr(lang, "total_balance"),
                        format_amount(balance.total_balance),
                        code
                    ),
                )
            } else if snapshot.checking {
                ("💰 -- CNY".to_string(), tr(lang, "checking").to_string())
            } else if let Some(error) = &snapshot.error {
                (
                    "💰 -- CNY".to_string(),
                    format!("{}: {error}", tr(lang, "error")),
                )
            } else {
                (
                    "💰 -- CNY".to_string(),
                    tr(lang, "balance_empty").to_string(),
                )
            };
        let last_check = snapshot
            .last_check
            .map(|last| relative_time(lang, last, now))
            .unwrap_or_else(|| tr(lang, "not_checked").to_string());
        let service_status_line = service_status_notification_label(lang, &snapshot.service_status);
        let estimated_line = rate
            .map(|rate| format!("📊 {}", estimated_availability_line(lang, rate)))
            .unwrap_or_else(|| {
                if lang == "en" {
                    "📊 Est. --".to_string()
                } else {
                    "📊 预计可用 --".to_string()
                }
            });
        let (
            og_error,
            og_rolling_percent,
            og_rolling_line,
            og_weekly_percent,
            og_weekly_line,
            og_monthly_percent,
            og_monthly_line,
        ) = match &snapshot.opencode {
            Some(quota) => (
                snapshot.opencode_error.clone().unwrap_or_default(),
                og_window_percent(quota.rolling.as_ref()),
                og_window_line(lang, quota.rolling.as_ref()),
                og_window_percent(quota.weekly.as_ref()),
                og_window_line(lang, quota.weekly.as_ref()),
                og_window_percent(quota.monthly.as_ref()),
                og_window_line(lang, quota.monthly.as_ref()),
            ),
            None => (
                snapshot.opencode_error.clone().unwrap_or_default(),
                0,
                "--".to_string(),
                0,
                "--".to_string(),
                0,
                "--".to_string(),
            ),
        };
        let (
            cc_error,
            cc_5h_percent,
            cc_5h_line,
            cc_weekly_percent,
            cc_weekly_line,
            cc_monthly_percent,
            cc_monthly_line,
        ) = match &snapshot.command_code {
            Some(quota) => (
                snapshot.command_code_error.clone().unwrap_or_default(),
                cc_window_percent(quota.five_hour.as_ref()),
                cc_window_line(lang, quota.five_hour.as_ref()),
                cc_window_percent(quota.weekly.as_ref()),
                cc_window_line(lang, quota.weekly.as_ref()),
                cc_window_percent(quota.monthly.as_ref()),
                cc_window_line(lang, quota.monthly.as_ref()),
            ),
            None => (
                snapshot.command_code_error.clone().unwrap_or_default(),
                0,
                "--".to_string(),
                0,
                "--".to_string(),
                0,
                "--".to_string(),
            ),
        };
        format!(
            "{{\"accent_color\":{},\"balance_line\":{},\"status_line\":{},\"last_check\":{},\"service_status_line\":{},\"estimated_line\":{},\"og_configured\":{},\"og_error\":{},\"og_rolling_percent\":{},\"og_rolling_line\":{},\"og_weekly_percent\":{},\"og_weekly_line\":{},\"og_monthly_percent\":{},\"og_monthly_line\":{},\"cc_configured\":{},\"cc_error\":{},\"cc_5h_percent\":{},\"cc_5h_line\":{},\"cc_weekly_percent\":{},\"cc_weekly_line\":{},\"cc_monthly_percent\":{},\"cc_monthly_line\":{}}}",
            json_string(&rainmeter_accent_color(snapshot)),
            json_string(&balance_line),
            json_string(&status_line),
            json_string(&last_check),
            json_string(&service_status_line),
            json_string(&estimated_line),
            if snapshot.opencode_configured { "true" } else { "false" },
            json_string(&og_error),
            og_rolling_percent,
            json_string(&og_rolling_line),
            og_weekly_percent,
            json_string(&og_weekly_line),
            og_monthly_percent,
            json_string(&og_monthly_line),
            if snapshot.command_code_configured { "true" } else { "false" },
            json_string(&cc_error),
            cc_5h_percent,
            json_string(&cc_5h_line),
            cc_weekly_percent,
            json_string(&cc_weekly_line),
            cc_monthly_percent,
            json_string(&cc_monthly_line),
        )
    }

    fn og_window_percent(usage: Option<&OpenCodeGoUsage>) -> i64 {
        usage
            .map(|usage| usage.usage_percent.clamp(0.0, 100.0) as i64)
            .unwrap_or(0)
    }

    fn og_window_line(lang: &str, usage: Option<&OpenCodeGoUsage>) -> String {
        match usage {
            Some(usage) => format!(
                "{:.0}% · {}",
                usage.usage_percent,
                format_reset_seconds(usage.reset_in_sec)
            ),
            None => tr(lang, "og_unavailable").to_string(),
        }
    }

    fn cc_window_percent(window: Option<&CommandCodeWindow>) -> i64 {
        window
            .filter(|window| window.cap > 0.0)
            .map(|window| ((window.used / window.cap) * 100.0).clamp(0.0, 100.0) as i64)
            .unwrap_or(0)
    }

    fn cc_window_line(lang: &str, window: Option<&CommandCodeWindow>) -> String {
        match window {
            Some(window) if window.cap > 0.0 => format!(
                "{:.1}/{:.1} · {}",
                window.used,
                window.cap,
                format_reset_seconds(window.reset_in_sec)
            ),
            _ => tr(lang, "cc_unavailable").to_string(),
        }
    }

    fn rainmeter_accent_color(snapshot: &RainmeterSnapshot) -> String {
        let key = if snapshot.checking {
            "nodata"
        } else if snapshot.error.is_some() {
            "low"
        } else if preferred_balance(&snapshot.balances).is_none() {
            "nodata"
        } else if preferred_balance(&snapshot.balances)
            .map(|(_, balance)| balance.total_balance < snapshot.config.threshold_yuan)
            .unwrap_or(false)
        {
            "low"
        } else if service_degraded(&snapshot.service_status) {
            "degraded"
        } else {
            "ok"
        };
        let [r, g, b, _] = theme_color(&snapshot.config, key).0;
        format!("{r},{g},{b}")
    }

    fn estimated_availability_line(lang: &str, rate: &ConsumptionRate) -> String {
        let days = (rate.busy_hours_left / 24.0).floor() as i64;
        let hours = (rate.busy_hours_left % 24.0).floor() as i64;
        if lang == "en" {
            format!(
                "Busy: {:.2}/hr | Est. {}d {}h remaining",
                rate.hourly_rate, days, hours
            )
        } else {
            format!(
                "忙时消耗 {:.2}/小时 | 预计可用 {} 天 {} 小时",
                rate.hourly_rate, days, hours
            )
        }
    }

    fn json_string(value: &str) -> String {
        serde_json::to_string(value).unwrap_or_else(|_| "\"\"".to_string())
    }

    struct SettingsWindow {
        base_config: AppConfig,
        window: nwg::Window,
        _tabs: nwg::TabsContainer,
        _account_tab: nwg::Tab,
        _general_tab: nwg::Tab,
        _history_tab: nwg::Tab,
        _subscription_tab: nwg::Tab,
        bold_font: nwg::Font,
        _group_credentials_label: nwg::Label,
        _credentials_sep: nwg::Frame,
        _group_query_label: nwg::Label,
        _query_sep: nwg::Frame,
        _group_general_label: nwg::Label,
        _general_sep: nwg::Frame,
        _group_proxy_label: nwg::Label,
        _proxy_sep: nwg::Frame,
        _group_appearance_label: nwg::Label,
        _appearance_sep: nwg::Frame,
        _group_og_label: nwg::Label,
        _og_sep: nwg::Frame,
        _og_api_key_label: nwg::Label,
        og_api_key_input: nwg::TextInput,
        og_show_api_key: nwg::CheckBox,
        _og_hint_box: nwg::TextBox,
        _og_rolling_label: nwg::Label,
        og_rolling_bar: nwg::ProgressBar,
        _og_rolling_value: nwg::Label,
        _og_weekly_label: nwg::Label,
        og_weekly_bar: nwg::ProgressBar,
        _og_weekly_value: nwg::Label,
        _og_monthly_label: nwg::Label,
        og_monthly_bar: nwg::ProgressBar,
        _og_monthly_value: nwg::Label,
        og_box: nwg::TextBox,
        refresh_og_button: nwg::Button,
        _group_cc_label: nwg::Label,
        _cc_sep: nwg::Frame,
        _cc_api_key_label: nwg::Label,
        cc_api_key_input: nwg::TextInput,
        cc_show_api_key: nwg::CheckBox,
        _cc_hint_box: nwg::TextBox,
        _cc_5h_label: nwg::Label,
        cc_5h_bar: nwg::ProgressBar,
        _cc_5h_value: nwg::Label,
        _cc_weekly_label: nwg::Label,
        cc_weekly_bar: nwg::ProgressBar,
        _cc_weekly_value: nwg::Label,
        _cc_monthly_label: nwg::Label,
        cc_monthly_bar: nwg::ProgressBar,
        _cc_monthly_value: nwg::Label,
        cc_box: nwg::TextBox,
        refresh_cc_button: nwg::Button,
        _api_label: nwg::Label,
        api_input: nwg::TextInput,
        show_key: nwg::CheckBox,
        _interval_label: nwg::Label,
        interval_input: nwg::TextInput,
        _threshold_label: nwg::Label,
        threshold_input: nwg::TextInput,
        _language_label: nwg::Label,
        language_combo: nwg::ComboBox<&'static str>,
        _alert_mode_label: nwg::Label,
        alert_mode_combo: nwg::ComboBox<&'static str>,
        api_alerts: nwg::CheckBox,
        _retention_label: nwg::Label,
        retention_input: nwg::TextInput,
        _export_path_label: nwg::Label,
        export_path_input: nwg::TextInput,
        proxy_enabled: nwg::CheckBox,
        _proxy_label: nwg::Label,
        proxy_input: nwg::TextInput,
        _theme_label: nwg::Label,
        theme_combo: nwg::ComboBox<&'static str>,
        icon_stroke: nwg::CheckBox,
        _custom_color_label: nwg::Label,
        ok_color_input: nwg::TextInput,
        low_color_input: nwg::TextInput,
        degraded_color_input: nwg::TextInput,
        nodata_color_input: nwg::TextInput,
        auto_start: nwg::CheckBox,
        _status_label: nwg::Label,
        _history_days_label: nwg::Label,
        history_days_input: nwg::TextInput,
        _history_currency_label: nwg::Label,
        history_currency_input: nwg::TextInput,
        history_box: nwg::TextBox,
        refresh_history_button: nwg::Button,
        export_history_button: nwg::Button,
        save_button: nwg::Button,
        cancel_button: nwg::Button,
        handler: RefCell<Option<nwg::EventHandler>>,
    }

    impl SettingsWindow {
        fn build(app: Rc<AppUi>) -> Result<Rc<Self>, nwg::NwgError> {
            let config = app.state.lock().unwrap().config.clone();
            let lang = config.ui_language.as_str();
            let checked = nwg::CheckBoxState::Checked;
            let unchecked = nwg::CheckBoxState::Unchecked;

            let mut window = Default::default();
            let mut tabs = Default::default();
            let mut account_tab = Default::default();
            let mut general_tab = Default::default();
            let mut history_tab = Default::default();
            let mut subscription_tab = Default::default();
            let mut bold_font = Default::default();
            let mut group_credentials_label = Default::default();
            let mut credentials_sep = Default::default();
            let mut group_query_label = Default::default();
            let mut query_sep = Default::default();
            let mut group_general_label = Default::default();
            let mut general_sep = Default::default();
            let mut group_proxy_label = Default::default();
            let mut proxy_sep = Default::default();
            let mut group_appearance_label = Default::default();
            let mut appearance_sep = Default::default();
            let mut group_og_label = Default::default();
            let mut og_sep = Default::default();
            let mut og_api_key_label = Default::default();
            let mut og_api_key_input = Default::default();
            let mut og_show_api_key = Default::default();
            let mut og_hint_box = Default::default();
            let mut og_rolling_label = Default::default();
            let mut og_rolling_bar = Default::default();
            let mut og_rolling_value = Default::default();
            let mut og_weekly_label = Default::default();
            let mut og_weekly_bar = Default::default();
            let mut og_weekly_value = Default::default();
            let mut og_monthly_label = Default::default();
            let mut og_monthly_bar = Default::default();
            let mut og_monthly_value = Default::default();
            let mut og_box = Default::default();
            let mut refresh_og_button = Default::default();
            let mut group_cc_label = Default::default();
            let mut cc_sep = Default::default();
            let mut cc_api_key_label = Default::default();
            let mut cc_api_key_input = Default::default();
            let mut cc_show_api_key = Default::default();
            let mut cc_hint_box = Default::default();
            let mut cc_5h_label = Default::default();
            let mut cc_5h_bar = Default::default();
            let mut cc_5h_value = Default::default();
            let mut cc_weekly_label = Default::default();
            let mut cc_weekly_bar = Default::default();
            let mut cc_weekly_value = Default::default();
            let mut cc_monthly_label = Default::default();
            let mut cc_monthly_bar = Default::default();
            let mut cc_monthly_value = Default::default();
            let mut cc_box = Default::default();
            let mut refresh_cc_button = Default::default();
            let mut api_label = Default::default();
            let mut api_input = Default::default();
            let mut show_key = Default::default();
            let mut interval_label = Default::default();
            let mut interval_input = Default::default();
            let mut threshold_label = Default::default();
            let mut threshold_input = Default::default();
            let mut language_label = Default::default();
            let mut language_combo = Default::default();
            let mut alert_mode_label = Default::default();
            let mut alert_mode_combo = Default::default();
            let mut api_alerts = Default::default();
            let mut retention_label = Default::default();
            let mut retention_input = Default::default();
            let mut export_path_label = Default::default();
            let mut export_path_input = Default::default();
            let mut proxy_enabled = Default::default();
            let mut proxy_label = Default::default();
            let mut proxy_input = Default::default();
            let mut theme_label = Default::default();
            let mut theme_combo = Default::default();
            let mut icon_stroke = Default::default();
            let mut custom_color_label = Default::default();
            let mut ok_color_input = Default::default();
            let mut low_color_input = Default::default();
            let mut degraded_color_input = Default::default();
            let mut nodata_color_input = Default::default();
            let mut auto_start = Default::default();
            let mut status_label = Default::default();
            let mut history_days_label = Default::default();
            let mut history_days_input = Default::default();
            let mut history_currency_label = Default::default();
            let mut history_currency_input = Default::default();
            let mut history_box = Default::default();
            let mut refresh_history_button = Default::default();
            let mut export_history_button = Default::default();
            let mut save_button = Default::default();
            let mut cancel_button = Default::default();

            nwg::Window::builder()
                .flags(nwg::WindowFlags::WINDOW | nwg::WindowFlags::VISIBLE)
                .size((520, 720))
                .center(true)
                .title(tr(lang, "settings_title"))
                .build(&mut window)?;
            nwg::TabsContainer::builder()
                .position((10, 10))
                .size((500, 635))
                .parent(&window)
                .build(&mut tabs)?;
            nwg::Font::builder()
                .family(ui_font_family())
                .size_absolute(12)
                .weight(700)
                .build(&mut bold_font)?;
            nwg::Tab::builder()
                .text(tr(lang, "account_tab"))
                .parent(&tabs)
                .build(&mut account_tab)?;
            nwg::Tab::builder()
                .text(tr(lang, "settings_tab"))
                .parent(&tabs)
                .build(&mut general_tab)?;
            nwg::Tab::builder()
                .text(tr(lang, "history_tab"))
                .parent(&tabs)
                .build(&mut history_tab)?;
            nwg::Tab::builder()
                .text(tr(lang, "subscription_tab"))
                .parent(&tabs)
                .build(&mut subscription_tab)?;
            let og_api_key = read_secure_value(OPENCODE_GO_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            let cc_api_key = read_secure_value(COMMAND_CODE_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            // ===== 账户页 =====
            nwg::Label::builder()
                .text(tr(lang, "group_credentials"))
                .position((20, 20))
                .size((200, 20))
                .parent(&account_tab)
                .build(&mut group_credentials_label)?;
            group_credentials_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 44))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&account_tab)
                .build(&mut credentials_sep)?;
            nwg::Label::builder()
                .text(tr(lang, "api_key_label"))
                .position((20, 62))
                .size((220, 20))
                .parent(&account_tab)
                .build(&mut api_label)?;
            nwg::TextInput::builder()
                .text(&config.api_key)
                .placeholder_text(
                    (!config.api_key.trim().is_empty()).then_some(API_KEY_PLACEHOLDER),
                )
                .position((20, 86))
                .size((460, 28))
                .parent(&account_tab)
                .focus(true)
                .build(&mut api_input)?;
            api_input.set_password_char(Some('*'));
            nwg::CheckBox::builder()
                .text(tr(lang, "show_key"))
                .position((20, 120))
                .size((200, 24))
                .parent(&account_tab)
                .check_state(unchecked)
                .build(&mut show_key)?;
            nwg::Label::builder()
                .text(tr(lang, "og_api_key_label"))
                .position((20, 154))
                .size((220, 20))
                .parent(&account_tab)
                .build(&mut og_api_key_label)?;
            nwg::TextInput::builder()
                .text(&og_api_key)
                .placeholder_text((!og_api_key.is_empty()).then_some(tr(lang, "og_api_key_hint")))
                .position((20, 178))
                .size((460, 28))
                .parent(&account_tab)
                .build(&mut og_api_key_input)?;
            og_api_key_input.set_password_char(Some('*'));
            nwg::CheckBox::builder()
                .text(tr(lang, "og_show_api_key"))
                .position((20, 212))
                .size((200, 24))
                .parent(&account_tab)
                .check_state(unchecked)
                .build(&mut og_show_api_key)?;
            nwg::TextBox::builder()
                .text(tr(lang, "og_hint"))
                .flags(
                    nwg::TextBoxFlags::VISIBLE
                        | nwg::TextBoxFlags::VSCROLL
                        | nwg::TextBoxFlags::TAB_STOP,
                )
                .readonly(true)
                .position((20, 246))
                .size((460, 40))
                .parent(&account_tab)
                .build(&mut og_hint_box)?;
            nwg::Label::builder()
                .text(tr(lang, "cc_api_key_label"))
                .position((20, 296))
                .size((220, 20))
                .parent(&account_tab)
                .build(&mut cc_api_key_label)?;
            nwg::TextInput::builder()
                .text(&cc_api_key)
                .placeholder_text((!cc_api_key.is_empty()).then_some(tr(lang, "cc_api_key_hint")))
                .position((20, 320))
                .size((460, 28))
                .parent(&account_tab)
                .build(&mut cc_api_key_input)?;
            cc_api_key_input.set_password_char(Some('*'));
            nwg::CheckBox::builder()
                .text(tr(lang, "cc_show_api_key"))
                .position((20, 354))
                .size((200, 24))
                .parent(&account_tab)
                .check_state(unchecked)
                .build(&mut cc_show_api_key)?;
            nwg::TextBox::builder()
                .text(tr(lang, "cc_hint"))
                .flags(
                    nwg::TextBoxFlags::VISIBLE
                        | nwg::TextBoxFlags::VSCROLL
                        | nwg::TextBoxFlags::TAB_STOP,
                )
                .readonly(true)
                .position((20, 384))
                .size((460, 48))
                .parent(&account_tab)
                .build(&mut cc_hint_box)?;

            // ===== 常规页：查询组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_query"))
                .position((20, 20))
                .size((200, 20))
                .parent(&general_tab)
                .build(&mut group_query_label)?;
            group_query_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 44))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&general_tab)
                .build(&mut query_sep)?;
            nwg::Label::builder()
                .text(tr(lang, "interval_label"))
                .position((20, 60))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut interval_label)?;
            nwg::TextInput::builder()
                .text(&config.interval_minutes.to_string())
                .position((250, 56))
                .size((230, 28))
                .parent(&general_tab)
                .build(&mut interval_input)?;
            nwg::Label::builder()
                .text(tr(lang, "threshold_label"))
                .position((20, 90))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut threshold_label)?;
            nwg::TextInput::builder()
                .text(&format!("{:.2}", config.threshold_yuan))
                .position((250, 86))
                .size((230, 28))
                .parent(&general_tab)
                .build(&mut threshold_input)?;
            nwg::Label::builder()
                .text(tr(lang, "alert_mode_label"))
                .position((20, 120))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut alert_mode_label)?;
            nwg::ComboBox::builder()
                .collection(vec![
                    tr(lang, "alert_mode_once"),
                    tr(lang, "alert_mode_always"),
                    tr(lang, "alert_mode_never"),
                ])
                .selected_index(Some(match config.alert_mode.as_str() {
                    "always" => 1,
                    "never" => 2,
                    _ => 0,
                }))
                .position((250, 116))
                .size((230, 100))
                .parent(&general_tab)
                .build(&mut alert_mode_combo)?;
            nwg::CheckBox::builder()
                .text(tr(lang, "api_alert_label"))
                .position((20, 150))
                .size((260, 24))
                .parent(&general_tab)
                .check_state(if config.api_alert_enabled {
                    checked
                } else {
                    unchecked
                })
                .build(&mut api_alerts)?;

            // ===== 常规页：通用组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_general"))
                .position((20, 180))
                .size((200, 20))
                .parent(&general_tab)
                .build(&mut group_general_label)?;
            group_general_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 204))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&general_tab)
                .build(&mut general_sep)?;
            nwg::Label::builder()
                .text(tr(lang, "language_label"))
                .position((20, 220))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut language_label)?;
            nwg::ComboBox::builder()
                .collection(vec!["中文", "English"])
                .selected_index(Some(if config.ui_language == "en" { 1 } else { 0 }))
                .position((250, 216))
                .size((230, 100))
                .parent(&general_tab)
                .build(&mut language_combo)?;
            nwg::CheckBox::builder()
                .text(tr(lang, "auto_start"))
                .position((20, 250))
                .size((220, 24))
                .parent(&general_tab)
                .check_state(if config.auto_start {
                    checked
                } else {
                    unchecked
                })
                .build(&mut auto_start)?;
            nwg::Label::builder()
                .text(tr(lang, "retention_label"))
                .position((20, 280))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut retention_label)?;
            nwg::TextInput::builder()
                .text(&config.retention_days.to_string())
                .position((250, 276))
                .size((230, 28))
                .parent(&general_tab)
                .build(&mut retention_input)?;
            nwg::Label::builder()
                .text(tr(lang, "export_path_label"))
                .position((20, 310))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut export_path_label)?;
            nwg::TextInput::builder()
                .text(&config.export_path)
                .placeholder_text(Some("%USERPROFILE%"))
                .position((250, 306))
                .size((230, 28))
                .parent(&general_tab)
                .build(&mut export_path_input)?;

            // ===== 常规页：代理组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_proxy"))
                .position((20, 340))
                .size((200, 20))
                .parent(&general_tab)
                .build(&mut group_proxy_label)?;
            group_proxy_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 364))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&general_tab)
                .build(&mut proxy_sep)?;
            nwg::CheckBox::builder()
                .text(tr(lang, "proxy_enable"))
                .position((20, 380))
                .size((260, 24))
                .parent(&general_tab)
                .check_state(if config.proxy_enabled {
                    checked
                } else {
                    unchecked
                })
                .build(&mut proxy_enabled)?;
            nwg::Label::builder()
                .text(tr(lang, "proxy_label"))
                .position((20, 410))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut proxy_label)?;
            nwg::TextInput::builder()
                .text(&config.http_proxy)
                .placeholder_text(Some(tr(lang, "proxy_placeholder")))
                .position((250, 406))
                .size((230, 28))
                .parent(&general_tab)
                .build(&mut proxy_input)?;

            // ===== 常规页：图标外观组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_appearance"))
                .position((20, 446))
                .size((200, 20))
                .parent(&general_tab)
                .build(&mut group_appearance_label)?;
            group_appearance_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 470))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&general_tab)
                .build(&mut appearance_sep)?;
            nwg::Label::builder()
                .text(tr(lang, "theme_label"))
                .position((20, 486))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut theme_label)?;
            nwg::ComboBox::builder()
                .collection(vec![
                    tr(lang, "theme_default"),
                    tr(lang, "theme_contrast"),
                    tr(lang, "theme_bright"),
                    tr(lang, "theme_dark_mode"),
                    tr(lang, "theme_mono"),
                    tr(lang, "theme_custom"),
                ])
                .selected_index(Some(match config.theme.as_str() {
                    "contrast" => 1,
                    "bright" => 2,
                    "dark_mode" => 3,
                    "mono" => 4,
                    "custom" => 5,
                    _ => 0,
                }))
                .position((250, 482))
                .size((230, 100))
                .parent(&general_tab)
                .build(&mut theme_combo)?;
            nwg::CheckBox::builder()
                .text(tr(lang, "icon_stroke_label"))
                .position((20, 516))
                .size((220, 24))
                .parent(&general_tab)
                .check_state(if config.icon_stroke {
                    checked
                } else {
                    unchecked
                })
                .build(&mut icon_stroke)?;
            nwg::Label::builder()
                .text(tr(lang, "custom_colors_label"))
                .position((20, 546))
                .size((220, 20))
                .parent(&general_tab)
                .build(&mut custom_color_label)?;
            let colors = custom_or_default_colors(&config);
            nwg::TextInput::builder()
                .text(colors.get("ok").map(String::as_str).unwrap_or("3c6966"))
                .position((20, 570))
                .size((100, 28))
                .parent(&general_tab)
                .build(&mut ok_color_input)?;
            nwg::TextInput::builder()
                .text(colors.get("low").map(String::as_str).unwrap_or("b9463c"))
                .position((135, 570))
                .size((100, 28))
                .parent(&general_tab)
                .build(&mut low_color_input)?;
            nwg::TextInput::builder()
                .text(
                    colors
                        .get("degraded")
                        .map(String::as_str)
                        .unwrap_or("78695a"),
                )
                .position((250, 570))
                .size((100, 28))
                .parent(&general_tab)
                .build(&mut degraded_color_input)?;
            nwg::TextInput::builder()
                .text(colors.get("nodata").map(String::as_str).unwrap_or("69696e"))
                .position((365, 570))
                .size((100, 28))
                .parent(&general_tab)
                .build(&mut nodata_color_input)?;

            nwg::Label::builder()
                .text("")
                .position((20, 604))
                .size((0, 0))
                .parent(&general_tab)
                .build(&mut status_label)?;
            let history_text =
                format_history_view(lang, config.retention_days, None, config.interval_minutes);
            nwg::Label::builder()
                .text(tr(lang, "history_days"))
                .position((20, 20))
                .size((45, 22))
                .parent(&history_tab)
                .build(&mut history_days_label)?;
            nwg::TextInput::builder()
                .text(&config.retention_days.to_string())
                .position((70, 16))
                .size((55, 28))
                .parent(&history_tab)
                .build(&mut history_days_input)?;
            nwg::Label::builder()
                .text(tr(lang, "history_currency_filter"))
                .position((140, 20))
                .size((60, 22))
                .parent(&history_tab)
                .build(&mut history_currency_label)?;
            nwg::TextInput::builder()
                .text("all")
                .position((205, 16))
                .size((70, 28))
                .parent(&history_tab)
                .build(&mut history_currency_input)?;
            nwg::Button::builder()
                .text(tr(lang, "refresh"))
                .position((290, 16))
                .size((86, 30))
                .parent(&history_tab)
                .build(&mut refresh_history_button)?;
            nwg::Button::builder()
                .text(tr(lang, "export"))
                .position((385, 16))
                .size((86, 30))
                .parent(&history_tab)
                .build(&mut export_history_button)?;
            nwg::TextBox::builder()
                .text(&history_text)
                .flags(
                    nwg::TextBoxFlags::VISIBLE
                        | nwg::TextBoxFlags::VSCROLL
                        | nwg::TextBoxFlags::HSCROLL
                        | nwg::TextBoxFlags::AUTOVSCROLL
                        | nwg::TextBoxFlags::AUTOHSCROLL
                        | nwg::TextBoxFlags::TAB_STOP,
                )
                .readonly(true)
                .position((20, 58))
                .size((455, 330))
                .parent(&history_tab)
                .build(&mut history_box)?;
            let og_box_text = if read_secure_value(OPENCODE_GO_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default()
                .is_empty()
            {
                tr(lang, "og_not_configured").to_string()
            } else {
                String::new()
            };
            let cc_box_text = if read_secure_value(COMMAND_CODE_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default()
                .is_empty()
            {
                tr(lang, "cc_not_configured").to_string()
            } else {
                String::new()
            };
            // ===== 订阅页：OpenCode Go 组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_og"))
                .position((20, 17))
                .size((200, 20))
                .parent(&subscription_tab)
                .build(&mut group_og_label)?;
            group_og_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 41))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&subscription_tab)
                .build(&mut og_sep)?;
            nwg::Button::builder()
                .text(tr(lang, "og_refresh"))
                .position((20, 52))
                .size((86, 30))
                .parent(&subscription_tab)
                .build(&mut refresh_og_button)?;
            nwg::Label::builder()
                .text(tr(lang, "og_window_5h"))
                .position((20, 92))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut og_rolling_label)?;
            nwg::ProgressBar::builder()
                .position((95, 90))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut og_rolling_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 92))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut og_rolling_value)?;
            nwg::Label::builder()
                .text(tr(lang, "og_window_weekly"))
                .position((20, 130))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut og_weekly_label)?;
            nwg::ProgressBar::builder()
                .position((95, 128))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut og_weekly_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 130))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut og_weekly_value)?;
            nwg::Label::builder()
                .text(tr(lang, "og_window_monthly"))
                .position((20, 168))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut og_monthly_label)?;
            nwg::ProgressBar::builder()
                .position((95, 166))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut og_monthly_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 168))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut og_monthly_value)?;
            nwg::TextBox::builder()
                .text(&og_box_text)
                .flags(
                    nwg::TextBoxFlags::VISIBLE
                        | nwg::TextBoxFlags::VSCROLL
                        | nwg::TextBoxFlags::AUTOVSCROLL
                        | nwg::TextBoxFlags::TAB_STOP,
                )
                .readonly(true)
                .position((20, 200))
                .size((440, 62))
                .parent(&subscription_tab)
                .build(&mut og_box)?;
            // ===== 订阅页：Command Code 组 =====
            nwg::Label::builder()
                .text(tr(lang, "group_cc"))
                .position((20, 272))
                .size((200, 20))
                .parent(&subscription_tab)
                .build(&mut group_cc_label)?;
            group_cc_label.set_font(Some(&bold_font));
            nwg::Frame::builder()
                .position((20, 296))
                .size((460, 1))
                .flags(nwg::FrameFlags::VISIBLE | nwg::FrameFlags::BORDER)
                .parent(&subscription_tab)
                .build(&mut cc_sep)?;
            nwg::Button::builder()
                .text(tr(lang, "cc_refresh"))
                .position((20, 307))
                .size((86, 30))
                .parent(&subscription_tab)
                .build(&mut refresh_cc_button)?;
            nwg::Label::builder()
                .text(tr(lang, "cc_window_5h"))
                .position((20, 347))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut cc_5h_label)?;
            nwg::ProgressBar::builder()
                .position((95, 345))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut cc_5h_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 347))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut cc_5h_value)?;
            nwg::Label::builder()
                .text(tr(lang, "cc_window_weekly"))
                .position((20, 385))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut cc_weekly_label)?;
            nwg::ProgressBar::builder()
                .position((95, 383))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut cc_weekly_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 385))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut cc_weekly_value)?;
            nwg::Label::builder()
                .text(tr(lang, "cc_window_monthly"))
                .position((20, 423))
                .size((70, 22))
                .parent(&subscription_tab)
                .build(&mut cc_monthly_label)?;
            nwg::ProgressBar::builder()
                .position((95, 421))
                .size((270, 14))
                .range(0..100)
                .pos(0)
                .parent(&subscription_tab)
                .build(&mut cc_monthly_bar)?;
            nwg::Label::builder()
                .text("--")
                .position((370, 423))
                .size((90, 22))
                .parent(&subscription_tab)
                .build(&mut cc_monthly_value)?;
            nwg::TextBox::builder()
                .text(&cc_box_text)
                .flags(
                    nwg::TextBoxFlags::VISIBLE
                        | nwg::TextBoxFlags::VSCROLL
                        | nwg::TextBoxFlags::AUTOVSCROLL
                        | nwg::TextBoxFlags::TAB_STOP,
                )
                .readonly(true)
                .position((20, 455))
                .size((440, 62))
                .parent(&subscription_tab)
                .build(&mut cc_box)?;
            nwg::Button::builder()
                .text(tr(lang, "save"))
                .position((300, 660))
                .size((86, 30))
                .parent(&window)
                .build(&mut save_button)?;
            nwg::Button::builder()
                .text(tr(lang, "cancel"))
                .position((395, 660))
                .size((86, 30))
                .parent(&window)
                .build(&mut cancel_button)?;

            let settings = Rc::new(Self {
                base_config: config.clone(),
                window,
                _tabs: tabs,
                _account_tab: account_tab,
                _general_tab: general_tab,
                _history_tab: history_tab,
                _subscription_tab: subscription_tab,
                bold_font,
                _group_credentials_label: group_credentials_label,
                _credentials_sep: credentials_sep,
                _group_query_label: group_query_label,
                _query_sep: query_sep,
                _group_general_label: group_general_label,
                _general_sep: general_sep,
                _group_proxy_label: group_proxy_label,
                _proxy_sep: proxy_sep,
                _group_appearance_label: group_appearance_label,
                _appearance_sep: appearance_sep,
                _group_og_label: group_og_label,
                _og_sep: og_sep,
                _og_api_key_label: og_api_key_label,
                og_api_key_input,
                og_show_api_key,
                _og_hint_box: og_hint_box,
                _og_rolling_label: og_rolling_label,
                og_rolling_bar,
                _og_rolling_value: og_rolling_value,
                _og_weekly_label: og_weekly_label,
                og_weekly_bar,
                _og_weekly_value: og_weekly_value,
                _og_monthly_label: og_monthly_label,
                og_monthly_bar,
                _og_monthly_value: og_monthly_value,
                og_box,
                refresh_og_button,
                _group_cc_label: group_cc_label,
                _cc_sep: cc_sep,
                _cc_api_key_label: cc_api_key_label,
                cc_api_key_input,
                cc_show_api_key,
                _cc_hint_box: cc_hint_box,
                _cc_5h_label: cc_5h_label,
                cc_5h_bar,
                _cc_5h_value: cc_5h_value,
                _cc_weekly_label: cc_weekly_label,
                cc_weekly_bar,
                _cc_weekly_value: cc_weekly_value,
                _cc_monthly_label: cc_monthly_label,
                cc_monthly_bar,
                _cc_monthly_value: cc_monthly_value,
                cc_box,
                refresh_cc_button,
                _api_label: api_label,
                api_input,
                show_key,
                _interval_label: interval_label,
                interval_input,
                _threshold_label: threshold_label,
                threshold_input,
                _language_label: language_label,
                language_combo,
                _alert_mode_label: alert_mode_label,
                alert_mode_combo,
                api_alerts,
                _retention_label: retention_label,
                retention_input,
                _export_path_label: export_path_label,
                export_path_input,
                proxy_enabled,
                _proxy_label: proxy_label,
                proxy_input,
                _theme_label: theme_label,
                theme_combo,
                icon_stroke,
                _custom_color_label: custom_color_label,
                ok_color_input,
                low_color_input,
                degraded_color_input,
                nodata_color_input,
                auto_start,
                _status_label: status_label,
                _history_days_label: history_days_label,
                history_days_input,
                _history_currency_label: history_currency_label,
                history_currency_input,
                history_box,
                refresh_history_button,
                export_history_button,
                save_button,
                cancel_button,
                handler: RefCell::new(None),
            });

            let weak_settings = Rc::downgrade(&settings);
            let weak_app = Rc::downgrade(&app);
            let handler =
                nwg::full_bind_event_handler(&settings.window.handle, move |evt, _data, handle| {
                    let Some(settings) = weak_settings.upgrade() else {
                        return;
                    };
                    let Some(app) = weak_app.upgrade() else {
                        return;
                    };
                    match evt {
                        nwg::Event::OnWindowClose if &handle == &settings.window => {
                            app.settings_closed()
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.cancel_button => {
                            app.settings_closed()
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.show_key => {
                            if settings.show_key.check_state() == nwg::CheckBoxState::Checked {
                                settings.api_input.set_password_char(None);
                            } else {
                                settings.api_input.set_password_char(Some('*'));
                            }
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.og_show_api_key => {
                            if settings.og_show_api_key.check_state() == nwg::CheckBoxState::Checked
                            {
                                settings.og_api_key_input.set_password_char(None);
                            } else {
                                settings.og_api_key_input.set_password_char(Some('*'));
                            }
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.refresh_og_button => {
                            settings.refresh_opencode_go();
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.cc_show_api_key => {
                            if settings.cc_show_api_key.check_state() == nwg::CheckBoxState::Checked
                            {
                                settings.cc_api_key_input.set_password_char(None);
                            } else {
                                settings.cc_api_key_input.set_password_char(Some('*'));
                            }
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.refresh_cc_button => {
                            settings.refresh_command_code();
                        }
                        nwg::Event::OnButtonClick
                            if &handle == &settings.refresh_history_button =>
                        {
                            settings.refresh_history();
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.export_history_button => {
                            settings.export_history();
                        }
                        nwg::Event::OnButtonClick if &handle == &settings.save_button => {
                            match settings.read_config() {
                                Ok(config) => {
                                    app.apply_config(config);
                                    app.settings_closed();
                                }
                                Err(message) => {
                                    let lang = settings.current_language();
                                    nwg::modal_error_message(
                                        &settings.window,
                                        tr(&lang, "warn_title"),
                                        &message,
                                    );
                                }
                            }
                        }
                        _ => {}
                    }
                });
            settings.handler.borrow_mut().replace(handler);
            Ok(settings)
        }

        fn refresh_opencode_go(&self) {
            let lang = self.current_language();
            let api_key = read_secure_value(OPENCODE_GO_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            if api_key.is_empty() {
                self.og_box.set_text(tr(&lang, "og_not_configured"));
                self.reset_opencode_go_bars();
                return;
            }
            let proxy = if self.proxy_enabled.check_state() == nwg::CheckBoxState::Checked {
                self.proxy_input.text().trim().to_string()
            } else {
                String::new()
            };
            self.og_box.set_text(tr(&lang, "og_checking"));
            self.reset_opencode_go_bars();
            match fetch_opencode_go_quota(&api_key, &proxy) {
                Ok(quota) => {
                    self.update_opencode_go_bars(&quota, &lang);
                    self.og_box.set_text(tr(&lang, "og_loaded"));
                }
                Err(error) => self
                    .og_box
                    .set_text(&format!("{} {error}", tr(&lang, "og_refresh_failed"))),
            }
        }

        fn update_opencode_go_bars(&self, quota: &OpenCodeGoQuota, lang: &str) {
            self.set_opencode_go_bar(
                &self.og_rolling_bar,
                &self._og_rolling_value,
                quota.rolling.as_ref(),
                lang,
            );
            self.set_opencode_go_bar(
                &self.og_weekly_bar,
                &self._og_weekly_value,
                quota.weekly.as_ref(),
                lang,
            );
            self.set_opencode_go_bar(
                &self.og_monthly_bar,
                &self._og_monthly_value,
                quota.monthly.as_ref(),
                lang,
            );
        }

        fn set_opencode_go_bar(
            &self,
            bar: &nwg::ProgressBar,
            value: &nwg::Label,
            usage: Option<&OpenCodeGoUsage>,
            lang: &str,
        ) {
            match usage {
                Some(usage) => {
                    bar.set_pos(usage.usage_percent.clamp(0.0, 100.0) as u32);
                    bar.set_state(match usage.usage_percent {
                        percent if percent >= 80.0 => nwg::ProgressBarState::Error,
                        percent if percent >= 60.0 => nwg::ProgressBarState::Paused,
                        _ => nwg::ProgressBarState::Normal,
                    });
                    value.set_text(&format!(
                        "{:.0}% · {}",
                        usage.usage_percent,
                        format_reset_seconds(usage.reset_in_sec)
                    ));
                }
                None => {
                    bar.set_pos(0);
                    bar.set_state(nwg::ProgressBarState::Normal);
                    value.set_text(tr(lang, "og_unavailable"));
                }
            }
        }

        fn reset_opencode_go_bars(&self) {
            for bar in [
                &self.og_rolling_bar,
                &self.og_weekly_bar,
                &self.og_monthly_bar,
            ] {
                bar.set_pos(0);
                bar.set_state(nwg::ProgressBarState::Normal);
            }
            for value in [
                &self._og_rolling_value,
                &self._og_weekly_value,
                &self._og_monthly_value,
            ] {
                value.set_text("--");
            }
        }

        fn refresh_command_code(&self) {
            let lang = self.current_language();
            let api_key = read_secure_value(COMMAND_CODE_API_KEY)
                .ok()
                .flatten()
                .unwrap_or_default();
            if api_key.is_empty() {
                self.cc_box.set_text(tr(&lang, "cc_not_configured"));
                self.reset_command_code_bars();
                return;
            }
            let proxy = if self.proxy_enabled.check_state() == nwg::CheckBoxState::Checked {
                self.proxy_input.text().trim().to_string()
            } else {
                String::new()
            };
            self.cc_box.set_text(tr(&lang, "cc_checking"));
            self.reset_command_code_bars();
            match fetch_command_code_quota(&api_key, &proxy) {
                Ok(quota) => {
                    self.update_command_code_bars(&quota, &lang);
                    self.cc_box.set_text(tr(&lang, "cc_loaded"));
                }
                Err(error) => self
                    .cc_box
                    .set_text(&format!("{} {error}", tr(&lang, "cc_refresh_failed"))),
            }
        }

        fn update_command_code_bars(&self, quota: &CommandCodeQuota, lang: &str) {
            self.set_command_code_bar(
                &self.cc_5h_bar,
                &self._cc_5h_value,
                quota.five_hour.as_ref(),
                lang,
            );
            self.set_command_code_bar(
                &self.cc_weekly_bar,
                &self._cc_weekly_value,
                quota.weekly.as_ref(),
                lang,
            );
            self.set_command_code_bar(
                &self.cc_monthly_bar,
                &self._cc_monthly_value,
                quota.monthly.as_ref(),
                lang,
            );
        }

        fn set_command_code_bar(
            &self,
            bar: &nwg::ProgressBar,
            value: &nwg::Label,
            window: Option<&CommandCodeWindow>,
            lang: &str,
        ) {
            match window {
                Some(window) => {
                    let percent = if window.cap > 0.0 {
                        (window.used / window.cap * 100.0).clamp(0.0, 100.0)
                    } else {
                        0.0
                    };
                    bar.set_pos(percent as u32);
                    bar.set_state(match percent {
                        percent if percent >= 80.0 => nwg::ProgressBarState::Error,
                        percent if percent >= 60.0 => nwg::ProgressBarState::Paused,
                        _ => nwg::ProgressBarState::Normal,
                    });
                    value.set_text(&format!(
                        "{:.1}/{:.1} · {}",
                        window.used,
                        window.cap,
                        format_reset_seconds(window.reset_in_sec)
                    ));
                }
                None => {
                    bar.set_pos(0);
                    bar.set_state(nwg::ProgressBarState::Normal);
                    value.set_text(tr(lang, "cc_unavailable"));
                }
            }
        }

        fn reset_command_code_bars(&self) {
            for bar in [&self.cc_5h_bar, &self.cc_weekly_bar, &self.cc_monthly_bar] {
                bar.set_pos(0);
                bar.set_state(nwg::ProgressBarState::Normal);
            }
            for value in [
                &self._cc_5h_value,
                &self._cc_weekly_value,
                &self._cc_monthly_value,
            ] {
                value.set_text("--");
            }
        }

        fn refresh_history(&self) {
            let (days, currency) = self.history_filters();
            let text = format_history_view(
                &self.current_language(),
                days,
                currency.as_deref(),
                self.base_config.interval_minutes,
            );
            self.history_box.set_text(&text);
        }

        fn export_history(&self) {
            let (days, currency) = self.history_filters();
            let lang = self.current_language();
            let export_path = self.export_path_input.text();
            match export_balance_history(days, currency.as_deref(), export_path.trim()) {
                Ok(path) => self.history_box.set_text(&format!(
                    "{} {}",
                    tr(&lang, "export_success"),
                    path.display()
                )),
                Err(error) => self
                    .history_box
                    .set_text(&format!("{} {error}", tr(&lang, "export_failed"))),
            }
        }

        fn history_filters(&self) -> (u64, Option<String>) {
            let days = self
                .history_days_input
                .text()
                .trim()
                .parse::<u64>()
                .unwrap_or(self.base_config.retention_days)
                .clamp(1, 3650);
            let currency = self.history_currency_input.text();
            let currency = currency.trim();
            let currency = if currency.is_empty() || currency.eq_ignore_ascii_case("all") {
                None
            } else {
                Some(currency.to_string())
            };
            (days, currency)
        }

        fn current_language(&self) -> String {
            if self.language_combo.selection() == Some(1) {
                "en".to_string()
            } else {
                "zh".to_string()
            }
        }

        fn read_config(&self) -> Result<AppConfig, String> {
            let mut config = self.base_config.clone();
            let lang = self.current_language();
            let api_key = self.api_input.text().trim().to_string();
            if api_key.is_empty() && config.api_key.trim().is_empty() {
                return Err(tr(&lang, "api_key_empty").to_string());
            }
            let og_api_key = self.og_api_key_input.text().trim().to_string();
            let cc_api_key = self.cc_api_key_input.text().trim().to_string();
            let interval_minutes = self
                .interval_input
                .text()
                .trim()
                .parse::<u64>()
                .map_err(|_| tr(&lang, "interval_number").to_string())?;
            if !(1..=1440).contains(&interval_minutes) {
                return Err(tr(&lang, "interval_range").to_string());
            }
            let threshold_yuan = self
                .threshold_input
                .text()
                .trim()
                .parse::<f64>()
                .map_err(|_| tr(&lang, "threshold_number").to_string())?;
            if !(0.0..=10000.0).contains(&threshold_yuan) {
                return Err(tr(&lang, "threshold_range").to_string());
            }
            let retention_days = self
                .retention_input
                .text()
                .trim()
                .parse::<u64>()
                .map_err(|_| tr(&lang, "retention_number").to_string())?;
            if !(1..=3650).contains(&retention_days) {
                return Err(tr(&lang, "retention_range").to_string());
            }
            config.interval_minutes = interval_minutes;
            config.threshold_yuan = threshold_yuan;
            config.ui_language = if self.language_combo.selection() == Some(1) {
                "en".to_string()
            } else {
                "zh".to_string()
            };
            config.auto_start = self.auto_start.check_state() == nwg::CheckBoxState::Checked;
            config.api_alert_enabled = self.api_alerts.check_state() == nwg::CheckBoxState::Checked;
            config.alert_mode = match self.alert_mode_combo.selection() {
                Some(1) => "always",
                Some(2) => "never",
                _ => "once",
            }
            .to_string();
            config.retention_days = retention_days;
            config.export_path = self.export_path_input.text().trim().to_string();
            config.http_proxy = self.proxy_input.text().trim().to_string();
            config.proxy_enabled = self.proxy_enabled.check_state() == nwg::CheckBoxState::Checked;
            config.theme = match self.theme_combo.selection() {
                Some(1) => "contrast",
                Some(2) => "bright",
                Some(3) => "dark_mode",
                Some(4) => "mono",
                Some(5) => "custom",
                _ => "default",
            }
            .to_string();
            config.icon_colors = if config.theme == "custom" {
                parse_icon_colors([
                    self.ok_color_input.text(),
                    self.low_color_input.text(),
                    self.degraded_color_input.text(),
                    self.nodata_color_input.text(),
                ])
                .map_err(|_| tr(&lang, "color_hex_error").to_string())?
            } else {
                BTreeMap::new()
            };
            config.icon_stroke = self.icon_stroke.check_state() == nwg::CheckBoxState::Checked;
            // 上面所有字段校验通过后才写凭据，避免校验失败时密钥已入库。
            if !api_key.is_empty() {
                store_secure_api_key(&api_key)?;
                config.api_key = api_key;
            }
            if !og_api_key.is_empty() {
                store_secure_value(OPENCODE_GO_API_KEY, &og_api_key)?;
            }
            if !cc_api_key.is_empty() {
                store_secure_value(COMMAND_CODE_API_KEY, &cc_api_key)?;
            }
            normalize_config(&mut config);
            Ok(config)
        }
    }

    impl Drop for SettingsWindow {
        fn drop(&mut self) {
            if let Some(handler) = self.handler.borrow_mut().take() {
                nwg::unbind_event_handler(&handler);
            }
        }
    }

    impl AppUi {}

    fn fetch_balance(api_key: &str, http_proxy: &str) -> Result<BTreeMap<String, Balance>, String> {
        let client = http_client(Duration::from_secs(15), http_proxy)?;
        let key = api_key.chars().filter(|c| c.is_ascii()).collect::<String>();
        let response = client
            .get("https://api.deepseek.com/user/balance")
            .header("Accept", "application/json")
            .bearer_auth(key)
            .send()
            .map_err(|e| e.to_string())?;
        if response.status() == StatusCode::UNAUTHORIZED {
            return Err("Invalid API Key (401 Unauthorized)".to_string());
        }
        let payload: ApiResponse = response
            .error_for_status()
            .map_err(|e| e.to_string())?
            .json()
            .map_err(|e| e.to_string())?;
        if payload.balance_infos.is_empty() {
            return Err("No balance information in response".to_string());
        }
        let mut balances = BTreeMap::new();
        for item in payload.balance_infos {
            balances.insert(
                item.currency,
                Balance {
                    total_balance: parse_amount(&item.total_balance),
                    granted_balance: parse_amount(&item.granted_balance),
                    topped_up_balance: parse_amount(&item.topped_up_balance),
                },
            );
        }
        Ok(balances)
    }

    fn fetch_opencode_go_quota(api_key: &str, http_proxy: &str) -> Result<OpenCodeGoQuota, String> {
        let client = http_client(Duration::from_secs(10), http_proxy)?;
        let response = client
            .get(OPENCODE_GO_API_URL)
            .header("Accept", "application/json")
            .header("Authorization", format!("Bearer {}", api_key.trim()))
            .send()
            .map_err(|e| format!("OpenCode Go request failed: {e}"))?;
        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().unwrap_or_default();
            let message = parse_opencode_go_api_error(&text)
                .unwrap_or_else(|| sanitize_opencode_go_message(&text));
            return Err(format!("OpenCode Go API error {status}: {message}"));
        }
        let payload: OpenCodeGoApiResponse = response
            .error_for_status()
            .map_err(|e| e.to_string())?
            .json()
            .map_err(|e| format!("OpenCode Go JSON parse failed: {e}"))?;
        let now = Local::now().timestamp();
        let quota = OpenCodeGoQuota {
            rolling: payload
                .usage
                .rolling
                .map(|window| api_window_to_usage(window, now)),
            weekly: payload
                .usage
                .weekly
                .map(|window| api_window_to_usage(window, now)),
            monthly: payload
                .usage
                .monthly
                .map(|window| api_window_to_usage(window, now)),
        };
        if quota.rolling.is_none() && quota.weekly.is_none() && quota.monthly.is_none() {
            return Err("OpenCode Go API returned no usage windows.".to_string());
        }
        Ok(quota)
    }

    fn api_window_to_usage(window: OpenCodeGoApiWindow, now: i64) -> OpenCodeGoUsage {
        let usage_percent = window.percent.clamp(0.0, 100.0);
        let reset_in_sec = window
            .resets_at
            .as_deref()
            .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
            .map(|dt| (dt.timestamp() - now).max(0))
            .unwrap_or(0);
        OpenCodeGoUsage {
            usage_percent,
            percent_remaining: (100.0 - usage_percent).max(0.0),
            reset_in_sec,
        }
    }

    fn fetch_command_code_quota(
        api_key: &str,
        http_proxy: &str,
    ) -> Result<CommandCodeQuota, String> {
        let client = http_client(Duration::from_secs(10), http_proxy)?;
        let organization_id = fetch_command_code_org_id(&client, api_key)?;
        let org_query = organization_id
            .map(|id| format!("?orgId={}", urlencode(&id)))
            .unwrap_or_default();
        let response = client
            .get(format!(
                "{COMMAND_CODE_API_BASE}alpha/billing/credits{org_query}"
            ))
            .header("Accept", "application/json")
            .header("Authorization", format!("Bearer {}", api_key.trim()))
            .send()
            .map_err(|e| format!("Command Code request failed: {e}"))?;
        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().unwrap_or_default();
            let message = sanitize_command_code_message(&text);
            return Err(format!("Command Code API error {status}: {message}"));
        }
        let payload: CommandCodeApiResponse = response
            .error_for_status()
            .map_err(|e| e.to_string())?
            .json()
            .map_err(|e| format!("Command Code JSON parse failed: {e}"))?;
        let now = Local::now().timestamp();
        let monthly = command_code_monthly_window(
            payload.credits.plan_id.as_deref(),
            payload.credits.monthly_credits,
        );
        let quota = CommandCodeQuota {
            five_hour: payload
                .window_limits
                .five_hour
                .map(|window| api_cc_window_to_window(window, now)),
            weekly: payload
                .window_limits
                .weekly
                .map(|window| api_cc_window_to_window(window, now)),
            monthly,
        };
        if quota.five_hour.is_none() && quota.weekly.is_none() && quota.monthly.is_none() {
            return Err("Command Code API returned no usage windows.".to_string());
        }
        Ok(quota)
    }

    fn fetch_command_code_org_id(
        client: &reqwest::blocking::Client,
        api_key: &str,
    ) -> Result<Option<String>, String> {
        let response = client
            .get(format!("{COMMAND_CODE_API_BASE}alpha/whoami"))
            .header("Accept", "application/json")
            .header("Authorization", format!("Bearer {}", api_key.trim()))
            .send()
            .map_err(|e| format!("Command Code request failed: {e}"))?;
        if !response.status().is_success() {
            return Ok(None);
        }
        let payload: CommandCodeApiWhoami = response
            .error_for_status()
            .map_err(|e| e.to_string())?
            .json()
            .map_err(|e| format!("Command Code JSON parse failed: {e}"))?;
        Ok(payload.org.and_then(|org| org.id))
    }

    fn api_cc_window_to_window(window: CommandCodeApiWindow, now: i64) -> CommandCodeWindow {
        CommandCodeWindow {
            used: window.used.max(0.0),
            cap: window.cap.max(0.0),
            reset_in_sec: epoch_to_reset_seconds(window.reset_at, now),
        }
    }

    fn epoch_to_reset_seconds(epoch: Option<f64>, now: i64) -> i64 {
        epoch
            .map(|value| {
                let seconds = if value >= 100_000_000_000.0 {
                    (value / 1000.0) as i64
                } else {
                    value as i64
                };
                (seconds - now).max(0)
            })
            .unwrap_or(0)
    }

    fn command_code_monthly_window(
        plan_id: Option<&str>,
        monthly_credits: Option<f64>,
    ) -> Option<CommandCodeWindow> {
        let is_goat = plan_id
            .map(|plan| {
                plan.replace('_', "-")
                    .to_ascii_lowercase()
                    .starts_with("individual-goat")
            })
            .unwrap_or(false);
        if is_goat {
            monthly_credits.map(|remaining| {
                let used = (GOAT_MONTHLY_CREDITS - remaining).clamp(0.0, GOAT_MONTHLY_CREDITS);
                CommandCodeWindow {
                    used,
                    cap: GOAT_MONTHLY_CREDITS,
                    reset_in_sec: 0,
                }
            })
        } else {
            // 非 GOAT 套餐：月度窗口不可靠，交给 UI 显示「不可用」
            None
        }
    }

    fn urlencode(value: &str) -> String {
        value
            .bytes()
            .map(|byte| match byte {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    (byte as char).to_string()
                }
                _ => format!("%{:02X}", byte),
            })
            .collect()
    }

    fn sanitize_command_code_message(text: &str) -> String {
        let cleaned: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
        if cleaned.is_empty() {
            "unknown".to_string()
        } else {
            cleaned.chars().take(120).collect()
        }
    }

    fn parse_opencode_go_api_error(text: &str) -> Option<String> {
        let value: serde_json::Value = serde_json::from_str(text).ok()?;
        let message = value.get("error")?.get("message")?.as_str()?;
        Some(message.to_string())
    }

    fn format_reset_seconds(secs: i64) -> String {
        if secs <= 0 {
            return "now".to_string();
        }
        let days = secs / 86400;
        let hours = (secs % 86400) / 3600;
        let minutes = (secs % 3600) / 60;
        let mut parts = Vec::new();
        if days > 0 {
            parts.push(format!("{days}d"));
        }
        if hours > 0 {
            parts.push(format!("{hours}h"));
        }
        if minutes > 0 {
            parts.push(format!("{minutes}m"));
        }
        if parts.is_empty() {
            parts.push(format!("{}s", secs % 60));
        }
        parts.join(" ")
    }

    fn sanitize_opencode_go_message(text: &str) -> String {
        let cleaned: String = text.split_whitespace().collect::<Vec<_>>().join(" ");
        if cleaned.is_empty() {
            "unknown".to_string()
        } else {
            cleaned.chars().take(120).collect()
        }
    }

    fn fetch_service_status(http_proxy: &str) -> String {
        let client = match http_client(Duration::from_secs(10), http_proxy) {
            Ok(client) => client,
            Err(error) => {
                log_line(&format!("API status client failed: {error}"));
                return "unknown".to_string();
            }
        };
        match fetch_flashduty_api_status(&client) {
            Ok(status) => status,
            Err(error) => {
                log_line(&format!("API status check failed: {error}"));
                "unknown".to_string()
            }
        }
    }

    fn http_client(
        timeout: Duration,
        http_proxy: &str,
    ) -> Result<reqwest::blocking::Client, String> {
        let mut builder = reqwest::blocking::Client::builder().timeout(timeout);
        let proxy = http_proxy.trim();
        if !proxy.is_empty() {
            builder = builder.proxy(Proxy::all(proxy).map_err(|e| e.to_string())?);
        }
        builder.build().map_err(|e| e.to_string())
    }

    fn effective_http_proxy(config: &AppConfig) -> &str {
        if config.proxy_enabled {
            config.http_proxy.trim()
        } else {
            ""
        }
    }

    fn fetch_flashduty_api_status(client: &reqwest::blocking::Client) -> Result<String, String> {
        let response = client
            .get("https://status.flashcat.cloud/deepseek")
            .header("Accept", "text/html,*/*")
            .header("User-Agent", "Mozilla/5.0")
            .send()
            .map_err(|e| format!("request failed: {e}"))?;
        let html = response
            .error_for_status()
            .map_err(|e| format!("HTTP status failed: {e}"))?
            .text()
            .map_err(|e| format!("HTML parse failed: {e}"))?;
        Ok(parse_flashduty_api_status(&html).to_string())
    }

    fn parse_flashduty_api_status(html: &str) -> &'static str {
        let full = html.replace("\\\"", "\"");
        full.split("\"name\"")
            .skip(1)
            .filter_map(|part| {
                let name = json_string_after_key(part, "")?;
                if name.to_ascii_lowercase().contains("api") {
                    json_string_after_key(part, "\"status\"").map(normalize_service_status)
                } else {
                    None
                }
            })
            .max_by_key(|status| status_rank(status))
            .unwrap_or("none")
    }

    fn json_string_after_key<'a>(text: &'a str, key: &str) -> Option<&'a str> {
        let text = if key.is_empty() {
            text
        } else {
            &text[text.find(key)? + key.len()..]
        };
        let start = text[text.find(':')? + 1..].trim_start().strip_prefix('"')?;
        start.split('"').next()
    }

    fn parse_amount(value: &str) -> f64 {
        value.parse::<f64>().unwrap_or(0.0)
    }

    fn format_amount(value: f64) -> String {
        format!("{value:.2}")
    }

    fn format_signed_amount(value: f64) -> String {
        if value >= 0.0 {
            format!("+{}", format_amount(value))
        } else {
            format_amount(value)
        }
    }

    fn preferred_balance(balances: &BTreeMap<String, Balance>) -> Option<(&String, &Balance)> {
        balances
            .get_key_value("CNY")
            .or_else(|| balances.iter().next())
    }

    fn normalize_service_status(value: &str) -> &'static str {
        match value {
            "none" | "operational" => "none",
            "minor" | "degraded" | "degraded_performance" => "minor",
            "major" | "partial_outage" => "major",
            "critical" | "full_outage" | "major_outage" => "critical",
            "maintenance" | "under_maintenance" => "maintenance",
            _ => "unknown",
        }
    }

    fn status_rank(status: &str) -> u8 {
        match status {
            "maintenance" => 1,
            "minor" => 2,
            "major" => 3,
            "critical" => 4,
            _ => 0,
        }
    }

    fn service_degraded(status: &str) -> bool {
        matches!(status, "maintenance" | "minor" | "major" | "critical")
    }

    fn service_status_text(lang: &str, status: &str) -> &'static str {
        match status {
            "none" => tr(lang, "status_none"),
            "minor" => tr(lang, "status_minor"),
            "major" => tr(lang, "status_major"),
            "critical" => tr(lang, "status_critical"),
            "maintenance" => tr(lang, "status_maintenance"),
            _ => tr(lang, "status_unknown"),
        }
    }

    fn service_status_notification_label(lang: &str, status: &str) -> String {
        let emoji = match status {
            "none" => "🟢",
            "minor" | "maintenance" => "🟡",
            "major" => "🟠",
            "critical" => "🔴",
            _ => "⚪",
        };
        format!("{} {}", emoji, service_status_text(lang, status))
    }

    fn is_low_balance(state: &RuntimeState) -> bool {
        preferred_balance(&state.balances)
            .map(|(_, balance)| balance.total_balance < state.config.threshold_yuan)
            .unwrap_or(false)
    }

    fn should_low_balance_alert(state: &mut RuntimeState, low_balance: bool) -> bool {
        if !low_balance {
            state.alert_suppressed = false;
            return false;
        }
        match state.config.alert_mode.as_str() {
            "never" => false,
            "always" => true,
            _ if state.alert_suppressed => false,
            _ => {
                state.alert_suppressed = true;
                true
            }
        }
    }

    fn format_balance_line(lang: &str, code: &str, balance: &Balance) -> String {
        if lang == "en" {
            format!(
                "{} {} (Topped {}, Granted {})",
                format_amount(balance.total_balance),
                code,
                format_amount(balance.topped_up_balance),
                format_amount(balance.granted_balance)
            )
        } else {
            format!(
                "{} {}（充值 {}，赠送 {}）",
                format_amount(balance.total_balance),
                code,
                format_amount(balance.topped_up_balance),
                format_amount(balance.granted_balance)
            )
        }
    }

    fn balance_notification_message(
        lang: &str,
        balances: &BTreeMap<String, Balance>,
        rate: Option<&ConsumptionRate>,
        error: Option<&str>,
        last_check: Option<DateTime<Local>>,
        service_status: &str,
        now: DateTime<Local>,
    ) -> String {
        let mut lines = Vec::new();
        if let Some((code, balance)) = preferred_balance(balances) {
            lines.push(format!("💰 {}", format_balance_line(lang, code, balance)));
            if let Some(rate) = rate {
                lines.push(format!("📊 {}", consumption_rate_line(lang, rate)));
            }
        }
        let separator = if lang == "en" { ": " } else { "：" };
        lines.push(format!(
            "📡 {}{}",
            tr(lang, "service_status"),
            service_status_notification_label(lang, service_status)
        ));
        if let Some(error) = error {
            lines.push(format!(
                "🕐 {}{}{}",
                tr(lang, "query_error"),
                separator,
                error
            ));
        } else if let Some(last) = last_check {
            lines.push(format!(
                "🕐 {}{}{}",
                tr(lang, "last_check"),
                separator,
                relative_time(lang, last, now)
            ));
        } else {
            lines.push(format!("🕐 {}", tr(lang, "not_checked")));
        }
        lines.join("\n")
    }

    fn relative_time(lang: &str, value: DateTime<Local>, now: DateTime<Local>) -> String {
        let seconds = (now - value).num_seconds().max(0);
        let zh = lang != "en";
        if seconds < 60 {
            return if zh { "刚刚" } else { "just now" }.to_string();
        }
        let (value, zh_unit, en_unit) = if seconds < 3600 {
            (seconds / 60, "分钟", "minutes")
        } else if seconds < 86400 {
            (seconds / 3600, "小时", "hours")
        } else {
            (seconds / 86400, "天", "days")
        };
        if zh {
            format!("{value} {zh_unit}前")
        } else {
            format!("{value} {en_unit} ago")
        }
    }

    fn icon_label(value: f64) -> String {
        let int_value = value.max(0.0) as u64;
        if int_value <= 99 {
            int_value.to_string()
        } else {
            "OK".to_string()
        }
    }

    fn write_tray_icon(
        path: &Path,
        label: &str,
        low_balance: bool,
        service_degraded: bool,
        config: &AppConfig,
    ) -> Result<(), String> {
        ensure_dir(&config_dir()).map_err(|e| e.to_string())?;
        let fill = match label {
            "!" => theme_color(config, "low"),
            "..." => theme_color(config, "nodata"),
            _ if low_balance => theme_color(config, "low"),
            _ if service_degraded => theme_color(config, "degraded"),
            _ => theme_color(config, "ok"),
        };
        let text_fill = text_color(fill);
        let mut image = RgbaImage::from_pixel(64, 64, Rgba([0, 0, 0, 0]));
        draw_rounded_square(&mut image, fill);
        if config.icon_stroke {
            draw_rounded_border(&mut image, text_fill);
        }
        if let Some(font) = load_font() {
            let font_size = if label.len() <= 1 {
                48.0
            } else if label.len() == 2 {
                44.0
            } else {
                34.0
            };
            let scale = Scale::uniform(font_size);
            let (x, y) = centered_text_position(&font, scale, label, 64, 64);
            draw_text_mut(&mut image, text_fill, x, y, scale, &font, label);
        }
        DynamicImage::ImageRgba8(image)
            .save_with_format(path, ImageFormat::Ico)
            .map_err(|e| e.to_string())
    }

    fn draw_rounded_square(image: &mut RgbaImage, fill: Rgba<u8>) {
        let size = 64i32;
        let radius = 12i32;
        for y in 0..size {
            for x in 0..size {
                if inside_rounded_rect(x, y, size, radius) {
                    image.put_pixel(x as u32, y as u32, fill);
                }
            }
        }
    }

    fn draw_rounded_border(image: &mut RgbaImage, color: Rgba<u8>) {
        let size = 64i32;
        let radius = 12i32;
        let inner = 5i32;
        for y in 0..size {
            for x in 0..size {
                if inside_rounded_rect(x, y, size, radius)
                    && !inside_rounded_rect(x - inner, y - inner, size - inner * 2, radius - inner)
                {
                    image.put_pixel(x as u32, y as u32, color);
                }
            }
        }
    }

    fn theme_color(config: &AppConfig, key: &str) -> Rgba<u8> {
        if config.theme == "custom" {
            if let Some(color) = config
                .icon_colors
                .get(key)
                .and_then(|value| rgba_from_hex(value))
            {
                return color;
            }
        }
        match (config.theme.as_str(), key) {
            ("contrast", "ok") => Rgba([45, 128, 116, 255]),
            ("contrast", "low") => Rgba([212, 52, 46, 255]),
            ("contrast", "degraded") => Rgba([139, 105, 20, 255]),
            ("contrast", "nodata") => Rgba([85, 85, 85, 255]),
            ("bright", "ok") => Rgba([200, 235, 230, 255]),
            ("bright", "low") => Rgba([245, 210, 205, 255]),
            ("bright", "degraded") => Rgba([235, 220, 205, 255]),
            ("bright", "nodata") => Rgba([215, 215, 220, 255]),
            ("dark_mode", "ok") => Rgba([80, 155, 148, 255]),
            ("dark_mode", "low") => Rgba([215, 100, 90, 255]),
            ("dark_mode", "degraded") => Rgba([155, 140, 115, 255]),
            ("dark_mode", "nodata") => Rgba([125, 125, 130, 255]),
            ("mono", "ok") => Rgba([85, 85, 85, 255]),
            ("mono", "low") => Rgba([34, 34, 34, 255]),
            ("mono", "degraded") => Rgba([119, 119, 119, 255]),
            ("mono", "nodata") => Rgba([153, 153, 153, 255]),
            (_, "low") => Rgba([185, 70, 60, 255]),
            (_, "degraded") => Rgba([120, 105, 90, 255]),
            (_, "nodata") => Rgba([105, 105, 110, 255]),
            _ => Rgba([60, 105, 102, 255]),
        }
    }

    fn rgba_from_hex(value: &str) -> Option<Rgba<u8>> {
        let value = value.trim().trim_start_matches('#');
        if value.len() != 6 {
            return None;
        }
        u32::from_str_radix(value, 16).ok().map(|rgb| {
            Rgba([
                ((rgb >> 16) & 0xff) as u8,
                ((rgb >> 8) & 0xff) as u8,
                (rgb & 0xff) as u8,
                255,
            ])
        })
    }

    fn text_color(fill: Rgba<u8>) -> Rgba<u8> {
        let [r, g, b, _] = fill.0;
        let lum = 0.299 * f64::from(r) + 0.587 * f64::from(g) + 0.114 * f64::from(b);
        if lum > 170.0 {
            Rgba([0, 0, 0, 255])
        } else {
            Rgba([255, 255, 255, 255])
        }
    }

    fn inside_rounded_rect(x: i32, y: i32, size: i32, radius: i32) -> bool {
        let left = x < radius;
        let right = x >= size - radius;
        let top = y < radius;
        let bottom = y >= size - radius;
        if !(left || right) || !(top || bottom) {
            return true;
        }
        let cx = if left { radius } else { size - radius - 1 };
        let cy = if top { radius } else { size - radius - 1 };
        let dx = x - cx;
        let dy = y - cy;
        dx * dx + dy * dy <= radius * radius
    }

    fn load_font() -> Option<Font<'static>> {
        thread_local! {
            static FONT_BYTES: RefCell<Option<Vec<u8>>> = RefCell::new(None);
        }
        // 字体只加载一次：托盘每次刷新都重读字体文件开销大，缓存在线程内复用。
        let bytes = FONT_BYTES.with(|cache| {
            let mut cached = cache.borrow_mut();
            if cached.is_none() {
                *cached = read_font_bytes();
            }
            cached.as_ref().cloned()
        });
        bytes.and_then(Font::try_from_vec)
    }

    fn read_font_bytes() -> Option<Vec<u8>> {
        for path in [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ] {
            if let Ok(bytes) = fs::read(path) {
                if Font::try_from_vec(bytes.clone()).is_some() {
                    return Some(bytes);
                }
            }
        }
        None
    }

    fn centered_text_position(
        font: &Font<'_>,
        scale: Scale,
        text: &str,
        width: i32,
        height: i32,
    ) -> (i32, i32) {
        let v_metrics = font.v_metrics(scale);
        let glyphs: Vec<_> = font
            .layout(text, scale, point(0.0, v_metrics.ascent))
            .collect();
        let mut min_x = 0;
        let mut min_y = 0;
        let mut max_x = 0;
        let mut max_y = 0;
        for bounds in glyphs.iter().filter_map(|g| g.pixel_bounding_box()) {
            min_x = min_x.min(bounds.min.x);
            min_y = min_y.min(bounds.min.y);
            max_x = max_x.max(bounds.max.x);
            max_y = max_y.max(bounds.max.y);
        }
        let text_width = max_x - min_x;
        let text_height = max_y - min_y;
        (
            (width - text_width) / 2 - min_x,
            (height - text_height) / 2 - min_y,
        )
    }

    fn config_dir() -> PathBuf {
        std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| user_home_dir().join("AppData").join("Roaming"))
            .join(APP_NAME)
    }

    fn user_home_dir() -> PathBuf {
        std::env::var_os("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."))
    }

    fn config_file() -> PathBuf {
        config_dir().join("config.json")
    }

    fn log_file() -> PathBuf {
        config_dir().join("app.log")
    }

    fn db_file() -> PathBuf {
        config_dir().join("balance_history.db")
    }

    fn db_marker_file() -> PathBuf {
        config_dir().join(".balance_history.db.initialized")
    }

    fn history_export_file(export_path: &str) -> PathBuf {
        let trimmed = export_path.trim();
        let dir = if trimmed.is_empty() {
            user_home_dir()
        } else if let Some(rest) = trimmed.strip_prefix("%USERPROFILE%") {
            // 输入框占位符提示 %USERPROFILE%，这里必须真正展开，否则会生成字面量目录。
            user_home_dir().join(rest.trim_start_matches(['\\', '/']))
        } else {
            PathBuf::from(trimmed)
        };
        dir.join(history_export_filename())
    }

    fn history_export_filename() -> String {
        format!(
            "deepseek-balance-history-{}.csv",
            Local::now().format("%Y%m%d")
        )
    }

    fn ensure_dir(path: &Path) -> std::io::Result<()> {
        fs::create_dir_all(path)
    }

    fn load_config() -> AppConfig {
        let path = config_file();
        let text = fs::read_to_string(path).ok();
        let missing_ui_language = text
            .as_ref()
            .map(|value| !value.contains("\"ui_language\""))
            .unwrap_or(false);
        let mut config = match text.as_deref().map(serde_json::from_str::<AppConfig>) {
            Some(Ok(config)) => config,
            Some(Err(error)) => {
                let backup = config_dir().join("config.json.corrupt");
                match fs::rename(config_file(), &backup) {
                    Ok(()) => log_line(&format!(
                        "Config parse failed: {error}. Corrupt file backed up to {}",
                        backup.display()
                    )),
                    Err(_) => log_line(&format!(
                        "Config parse failed: {error}. Could not back up the corrupt file."
                    )),
                }
                AppConfig::default()
            }
            None => AppConfig::default(),
        };
        let legacy_api_key = config.api_key.trim().to_string();
        let had_legacy_api_key = !legacy_api_key.is_empty();
        if missing_ui_language && matches!(config.language.as_str(), "zh" | "en") {
            config.ui_language = config.language.clone();
        }
        normalize_config(&mut config);
        let mut should_save_config = missing_ui_language;
        config.api_key = if had_legacy_api_key {
            if store_secure_api_key(&legacy_api_key).is_ok() {
                should_save_config = true;
            } else {
                log_line("Failed to migrate legacy API key into secure_settings");
            }
            legacy_api_key
        } else {
            match read_secure_api_key() {
                Ok(Some(key)) => key,
                Ok(None) => String::new(),
                Err(error) => {
                    log_line(&format!("Failed to read encrypted API key: {error}"));
                    String::new()
                }
            }
        };
        if should_save_config {
            let _ = save_config(&config);
        }
        config
    }

    fn normalize_config(config: &mut AppConfig) {
        if config.alert_mode == default_alert_mode() {
            if let Some(value) = config.extra.remove("enable_alerts") {
                config.alert_mode = if value.as_bool() == Some(false) {
                    "never".to_string()
                } else {
                    "once".to_string()
                };
            }
        } else {
            config.extra.remove("enable_alerts");
        }
        if let Some(value) = config.extra.remove("log_retention_days") {
            if let Some(days) = value.as_u64() {
                config.retention_days = days;
            }
        }
        config.interval_minutes = config.interval_minutes.clamp(1, 1440);
        config.threshold_yuan = config.threshold_yuan.clamp(0.0, 10000.0);
        config.retention_days = config.retention_days.clamp(1, 3650);
        if config.language != default_lang() {
            config.language = default_lang();
        }
        if !matches!(config.ui_language.as_str(), "zh" | "en") {
            config.ui_language = default_ui_lang();
        }
        if !matches!(config.alert_mode.as_str(), "never" | "always" | "once") {
            config.alert_mode = default_alert_mode();
        }
        config.export_path = config.export_path.trim().to_string();
        if !matches!(
            config.theme.as_str(),
            "default" | "contrast" | "bright" | "dark_mode" | "mono" | "custom"
        ) {
            config.theme = default_theme();
        }
    }

    fn save_config(config: &AppConfig) -> std::io::Result<()> {
        ensure_dir(&config_dir())?;
        let mut safe = config.clone();
        safe.api_key.clear();
        let file = File::create(config_file())?;
        serde_json::to_writer_pretty(file, &safe)?;
        Ok(())
    }

    fn read_secure_api_key() -> Result<Option<String>, String> {
        let conn = open_history_db()?;
        let encrypted = match conn.query_row(
            "SELECT value FROM secure_settings WHERE key = ?1",
            params!["api_key"],
            |row| row.get::<_, Vec<u8>>(0),
        ) {
            Ok(value) => value,
            Err(SqlError::QueryReturnedNoRows) => return Ok(None),
            Err(error) => return Err(error.to_string()),
        };
        let value = decrypt_secret(&encrypted)?;
        Ok((!value.trim().is_empty()).then_some(value))
    }

    fn store_secure_api_key(api_key: &str) -> Result<(), String> {
        let encrypted = encrypt_secret(api_key.trim())?;
        let conn = open_history_db()?;
        conn.execute(
            "INSERT OR REPLACE INTO secure_settings (key, value, updated_at) VALUES (?1, ?2, ?3)",
            params![
                "api_key",
                encrypted,
                Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    fn read_secure_value(key: &str) -> Result<Option<String>, String> {
        let conn = open_history_db()?;
        let encrypted = match conn.query_row(
            "SELECT value FROM secure_settings WHERE key = ?1",
            params![key],
            |row| row.get::<_, Vec<u8>>(0),
        ) {
            Ok(value) => value,
            Err(SqlError::QueryReturnedNoRows) => return Ok(None),
            Err(error) => return Err(error.to_string()),
        };
        let value = decrypt_secret(&encrypted)?;
        Ok((!value.trim().is_empty()).then_some(value))
    }

    fn store_secure_value(key: &str, value: &str) -> Result<(), String> {
        let encrypted = encrypt_secret(value.trim())?;
        let conn = open_history_db()?;
        conn.execute(
            "INSERT OR REPLACE INTO secure_settings (key, value, updated_at) VALUES (?1, ?2, ?3)",
            params![
                key,
                encrypted,
                Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
            ],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    fn encrypt_secret(plaintext: &str) -> Result<Vec<u8>, String> {
        let mut input = plaintext.as_bytes().to_vec();
        let mut input_blob = DataBlob {
            cb_data: input.len() as u32,
            pb_data: input.as_mut_ptr(),
        };
        let mut output_blob = DataBlob {
            cb_data: 0,
            pb_data: ptr::null_mut(),
        };
        let ok = unsafe {
            CryptProtectData(
                &mut input_blob,
                ptr::null(),
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                0,
                &mut output_blob,
            )
        };
        if ok == 0 {
            return Err("Failed to encrypt API key with Windows DPAPI".to_string());
        }
        copy_blob_and_free(output_blob)
    }

    fn decrypt_secret(encrypted: &[u8]) -> Result<String, String> {
        let mut input = encrypted.to_vec();
        let mut input_blob = DataBlob {
            cb_data: input.len() as u32,
            pb_data: input.as_mut_ptr(),
        };
        let mut output_blob = DataBlob {
            cb_data: 0,
            pb_data: ptr::null_mut(),
        };
        let ok = unsafe {
            CryptUnprotectData(
                &mut input_blob,
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                ptr::null_mut(),
                0,
                &mut output_blob,
            )
        };
        if ok == 0 {
            return Err("Failed to decrypt API key with Windows DPAPI".to_string());
        }
        let bytes = copy_blob_and_free(output_blob)?;
        String::from_utf8(bytes).map_err(|e| e.to_string())
    }

    fn copy_blob_and_free(blob: DataBlob) -> Result<Vec<u8>, String> {
        if blob.pb_data.is_null() {
            return Err("Windows DPAPI returned empty data".to_string());
        }
        let bytes =
            unsafe { std::slice::from_raw_parts(blob.pb_data, blob.cb_data as usize).to_vec() };
        unsafe {
            LocalFree(blob.pb_data.cast());
        }
        Ok(bytes)
    }

    fn open_url(target: &str) -> Result<(), String> {
        Command::new("cmd")
            .args(["/C", "start", ""])
            .arg(target)
            .spawn()
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    fn log_line(message: &str) {
        if ensure_dir(&config_dir()).is_err() {
            return;
        }
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .append(true)
            .open(log_file())
        {
            let _ = writeln!(
                file,
                "[{}] {}",
                Local::now().format("%Y-%m-%d %H:%M:%S"),
                message
            );
        }
    }

    fn save_balance_history(
        balances: &BTreeMap<String, Balance>,
        service_status: &str,
    ) -> Result<(), String> {
        let mut conn = open_history_db()?;
        let timestamp = Local::now().format("%Y-%m-%d %H:%M:%S").to_string();
        let dedup_cutoff = (Local::now() - ChronoDuration::seconds(HISTORY_DEDUP_SECONDS))
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();
        let tx = conn.transaction().map_err(|e| e.to_string())?;
        for (currency, balance) in balances {
            let duplicate: i64 = tx
                .query_row(
                    "SELECT EXISTS(
                        SELECT 1 FROM balance_history
                        WHERE currency = ?1
                          AND timestamp >= ?2
                          AND ABS(total - ?3) < 0.000001
                          AND ABS(topped - ?4) < 0.000001
                          AND ABS(granted - ?5) < 0.000001
                        LIMIT 1
                    )",
                    params![
                        currency.as_str(),
                        &dedup_cutoff,
                        balance.total_balance,
                        balance.topped_up_balance,
                        balance.granted_balance
                    ],
                    |row| row.get(0),
                )
                .map_err(|e| e.to_string())?;
            if duplicate != 0 {
                continue;
            }
            tx.execute(
                "INSERT INTO balance_history (timestamp, currency, total, topped, granted, service_status) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    &timestamp,
                    currency.as_str(),
                    balance.total_balance,
                    balance.topped_up_balance,
                    balance.granted_balance,
                    service_status
                ],
            )
            .map_err(|e| e.to_string())?;
        }
        tx.commit().map_err(|e| e.to_string())
    }

    fn recent_balance_history(days: u64, limit: usize) -> Result<Vec<HistoryRecord>, String> {
        history_records(days, None, limit)
    }

    fn history_records(
        days: u64,
        currency: Option<&str>,
        limit: usize,
    ) -> Result<Vec<HistoryRecord>, String> {
        let conn = open_history_db()?;
        let cutoff = (Local::now() - ChronoDuration::days(days as i64))
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();
        let limit = i64::try_from(limit).unwrap_or(i64::MAX);
        let mut stmt;
        let rows = if let Some(currency) = currency {
            stmt = conn
                .prepare(
                    "SELECT timestamp, currency, total, topped, granted, service_status FROM balance_history \
                     WHERE timestamp >= ?1 AND currency = ?2 ORDER BY timestamp ASC LIMIT ?3",
                )
                .map_err(|e| e.to_string())?;
            stmt.query_map(params![cutoff, currency, limit], history_record_from_row)
                .map_err(|e| e.to_string())?
        } else {
            stmt = conn
                .prepare(
                    "SELECT timestamp, currency, total, topped, granted, service_status FROM balance_history \
                     WHERE timestamp >= ?1 ORDER BY timestamp ASC LIMIT ?2",
                )
                .map_err(|e| e.to_string())?;
            stmt.query_map(params![cutoff, limit], history_record_from_row)
                .map_err(|e| e.to_string())?
        };
        let mut records = Vec::new();
        for row in rows {
            records.push(row.map_err(|e| e.to_string())?);
        }
        Ok(records)
    }

    fn history_record_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<HistoryRecord> {
        Ok(HistoryRecord {
            timestamp: row.get(0)?,
            currency: row.get(1)?,
            total: row.get(2)?,
            topped: row.get(3)?,
            granted: row.get(4)?,
            service_status: row.get(5)?,
        })
    }

    fn format_history_view(
        lang: &str,
        days: u64,
        currency: Option<&str>,
        interval_minutes: u64,
    ) -> String {
        let records = history_records(days, currency, usize::MAX).unwrap_or_default();
        if records.is_empty() {
            return tr(lang, "history_empty").to_string();
        }
        let mut lines = vec![format!(
            "{}: {} | {}: {}",
            tr(lang, "history_days"),
            days,
            tr(lang, "history_currency_filter"),
            currency.unwrap_or_else(|| tr(lang, "history_all"))
        )];
        for item in summarize_history(&records) {
            lines.push(format!(
                "{}: {} | {} {} | {} {} | {} {}/{} | {} {} | {} {}",
                item.currency,
                item.records,
                tr(lang, "history_trend"),
                trend_label(lang, item.change_total),
                tr(lang, "history_total"),
                format_amount(item.latest_total),
                tr(lang, "history_range"),
                format_amount(item.min_total),
                format_amount(item.max_total),
                tr(lang, "history_avg"),
                format_amount(item.avg_total),
                tr(lang, "history_change"),
                format_signed_amount(item.change_total)
            ));
            lines.push(format!(
                "  {} - {} | {} {} | {} {}",
                item.first_time,
                item.last_time,
                tr(lang, "topped_up"),
                format_amount(item.latest_topped),
                tr(lang, "granted"),
                format_amount(item.latest_granted)
            ));
        }
        if let Ok(Some(rate)) = consumption_rate_with_fallback(days, interval_minutes) {
            lines.push(consumption_rate_line(lang, &rate));
        } else {
            lines.push(tr(lang, "not_enough_data").to_string());
        }
        lines.push(String::new());
        lines.push(tr(lang, "history_chart").to_string());
        lines.extend(history_chart(lang, &records));
        lines.join("\r\n")
    }

    fn summarize_history(records: &[HistoryRecord]) -> Vec<HistorySummary> {
        let mut grouped: BTreeMap<String, Vec<&HistoryRecord>> = BTreeMap::new();
        for record in records {
            grouped
                .entry(record.currency.clone())
                .or_default()
                .push(record);
        }
        grouped
            .into_iter()
            .filter_map(|(currency, items)| {
                let first = items.first()?;
                let latest = items.last()?;
                let min_total = items
                    .iter()
                    .map(|record| record.total)
                    .fold(f64::INFINITY, f64::min);
                let max_total = items
                    .iter()
                    .map(|record| record.total)
                    .fold(f64::NEG_INFINITY, f64::max);
                let avg_total =
                    items.iter().map(|record| record.total).sum::<f64>() / items.len() as f64;
                Some(HistorySummary {
                    currency,
                    records: items.len(),
                    first_time: first.timestamp.clone(),
                    last_time: latest.timestamp.clone(),
                    latest_total: latest.total,
                    latest_topped: latest.topped,
                    latest_granted: latest.granted,
                    min_total,
                    max_total,
                    avg_total,
                    change_total: latest.total - first.total,
                })
            })
            .collect()
    }

    fn consumption_rate(
        hours: i64,
        interval_minutes: u64,
    ) -> Result<Option<ConsumptionRate>, String> {
        let conn = open_history_db()?;
        let currency = match conn.query_row(
            "SELECT currency FROM balance_history
             GROUP BY currency
             ORDER BY MAX(timestamp) DESC, MAX(total) DESC
             LIMIT 1",
            [],
            |row| row.get::<_, String>(0),
        ) {
            Ok(value) => value,
            Err(SqlError::QueryReturnedNoRows) => return Ok(None),
            Err(error) => return Err(error.to_string()),
        };
        let cutoff = (Local::now() - ChronoDuration::hours(hours.max(1)))
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();
        let mut stmt = conn
            .prepare(
                "SELECT timestamp, currency, total, topped, granted, service_status
                 FROM balance_history
                 WHERE timestamp >= ?1 AND currency = ?2
                 ORDER BY timestamp ASC",
            )
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map(params![cutoff, currency], history_record_from_row)
            .map_err(|e| e.to_string())?;
        let mut records = Vec::new();
        for row in rows {
            records.push(row.map_err(|e| e.to_string())?);
        }
        consumption_rate_from_records(&records, interval_minutes)
    }

    fn consumption_rate_with_fallback(
        retention_days: u64,
        interval_minutes: u64,
    ) -> Result<Option<ConsumptionRate>, String> {
        if let Some(rate) = consumption_rate(7 * 24, interval_minutes)? {
            return Ok(Some(rate));
        }
        let fallback_hours = retention_days
            .max(1)
            .saturating_mul(24)
            .min(i64::MAX as u64) as i64;
        if fallback_hours <= 7 * 24 {
            return Ok(None);
        }
        consumption_rate(fallback_hours, interval_minutes)
    }

    fn consumption_rate_from_records(
        records: &[HistoryRecord],
        interval_minutes: u64,
    ) -> Result<Option<ConsumptionRate>, String> {
        if records.len() < 2 {
            return Ok(None);
        }

        // Parse records and get currency
        let currency = records[0].currency.clone();
        let parsed: Vec<_> = records
            .iter()
            .map(|r| {
                let ts = NaiveDateTime::parse_from_str(&r.timestamp, "%Y-%m-%d %H:%M:%S")
                    .map_err(|e| e.to_string())?;
                Ok((ts, r.topped))
            })
            .collect::<Result<Vec<_>, String>>()?;

        // Determine busy threshold m (in seconds)
        // m = max(30, 2 * interval_minutes) minutes
        let m_minutes = 30i64.max(2 * interval_minutes as i64);
        let m_sec = (m_minutes * 60) as f64;

        // --- Build busy intervals ----------------------------------------
        let mut intervals: Vec<(f64, NaiveDateTime, f64, NaiveDateTime)> = Vec::new();
        let mut seg_start_val = parsed[0].1;
        let mut seg_start_ts = parsed[0].0;
        let mut prev_val = seg_start_val;
        let mut prev_ts = seg_start_ts;
        let mut eq_start_idx: Option<usize> = None; // index where current equal run began

        for i in 1..parsed.len() {
            let (curr_ts, curr_val) = parsed[i];
            let gap_sec = (curr_ts - prev_ts).num_seconds() as f64;

            if curr_val > prev_val {
                // Rule 1 — top-up: close previous interval, start fresh
                if let Some(eq_idx) = eq_start_idx {
                    let eq_dur = (prev_ts - parsed[eq_idx].0).num_seconds() as f64;
                    if eq_dur > m_sec {
                        if parsed[eq_idx].0 > seg_start_ts {
                            intervals.push((
                                seg_start_val,
                                seg_start_ts,
                                parsed[eq_idx].1,
                                parsed[eq_idx].0,
                            ));
                        }
                        seg_start_val = curr_val;
                        seg_start_ts = curr_ts;
                        prev_val = curr_val;
                        prev_ts = curr_ts;
                        eq_start_idx = None;
                        continue;
                    }
                    eq_start_idx = None;
                }

                if prev_ts > seg_start_ts {
                    intervals.push((seg_start_val, seg_start_ts, prev_val, prev_ts));
                }
                seg_start_val = curr_val;
                seg_start_ts = curr_ts;
            } else if curr_val < prev_val {
                if gap_sec > m_sec {
                    // Rule 2 — long idle gap: slice.
                    // Process any pending equal run FIRST so long flat
                    // periods aren't smuggled into the interval.
                    if let Some(eq_idx) = eq_start_idx {
                        let eq_dur = (prev_ts - parsed[eq_idx].0).num_seconds() as f64;
                        if eq_dur > m_sec {
                            if parsed[eq_idx].0 > seg_start_ts {
                                intervals.push((
                                    seg_start_val,
                                    seg_start_ts,
                                    parsed[eq_idx].1,
                                    parsed[eq_idx].0,
                                ));
                            }
                            seg_start_val = prev_val;
                            seg_start_ts = prev_ts;
                        }
                        eq_start_idx = None;
                    }
                    if prev_ts > seg_start_ts {
                        intervals.push((seg_start_val, seg_start_ts, prev_val, prev_ts));
                    }
                    seg_start_val = curr_val;
                    seg_start_ts = curr_ts;
                } else {
                    // Normal consumption — may follow a short equal run
                    if let Some(eq_idx) = eq_start_idx {
                        let eq_dur = (prev_ts - parsed[eq_idx].0).num_seconds() as f64;
                        if eq_dur > m_sec {
                            // Rule 3 — long flat: discard it
                            if parsed[eq_idx].0 > seg_start_ts {
                                intervals.push((
                                    seg_start_val,
                                    seg_start_ts,
                                    parsed[eq_idx].1,
                                    parsed[eq_idx].0,
                                ));
                            }
                            seg_start_val = curr_val;
                            seg_start_ts = curr_ts;
                            prev_val = curr_val;
                            prev_ts = curr_ts;
                            eq_start_idx = None;
                            continue;
                        }
                        eq_start_idx = None;
                    }
                }
            } else {
                // curr_val == prev_val — Rule 3: track equal run
                if eq_start_idx.is_none() {
                    eq_start_idx = Some(i - 1);
                }
            }

            prev_val = curr_val;
            prev_ts = curr_ts;
        }

        // Handle trailing equal run (never resolved because value didn't change)
        if let Some(eq_idx) = eq_start_idx {
            let eq_dur = (parsed.last().unwrap().0 - parsed[eq_idx].0).num_seconds() as f64;
            if eq_dur > m_sec {
                if parsed[eq_idx].0 > seg_start_ts {
                    intervals.push((
                        seg_start_val,
                        seg_start_ts,
                        parsed[eq_idx].1,
                        parsed[eq_idx].0,
                    ));
                }
                seg_start_ts = parsed.last().unwrap().0; // prevent double-add below
            }
        }

        // Close final interval
        if parsed.last().unwrap().0 > seg_start_ts {
            intervals.push((seg_start_val, seg_start_ts, prev_val, prev_ts));
        }

        // --- Weighted average of hourly rates ----------------------------
        let mut total_weight = 0.0;
        let mut weighted_sum = 0.0;
        for (sv, st, ev, et) in intervals {
            if ev >= sv {
                continue;
            }
            let delta_h = (et - st).num_seconds() as f64 / 3600.0;
            if delta_h < 0.01 {
                continue;
            }
            let hourly_rate = (sv - ev) / delta_h;
            weighted_sum += hourly_rate * delta_h;
            total_weight += delta_h;
        }

        if total_weight == 0.0 {
            return Ok(None);
        }

        let avg_hourly = weighted_sum / total_weight;
        if avg_hourly <= 0.0 {
            return Ok(None);
        }

        let remaining = parsed.last().unwrap().1;
        let busy_hours = remaining / avg_hourly;
        Ok(Some(ConsumptionRate {
            hourly_rate: avg_hourly,
            busy_hours_left: busy_hours,
            currency,
        }))
    }

    fn consumption_rate_line(lang: &str, rate: &ConsumptionRate) -> String {
        let days = (rate.busy_hours_left / 24.0).floor() as i64;
        let hours = (rate.busy_hours_left % 24.0).floor() as i64;
        if lang == "en" {
            format!(
                "Busy: {:.2}/hr | Est. {}d {}h remaining",
                rate.hourly_rate, days, hours
            )
        } else {
            format!(
                "忙时消耗 {:.2}/小时 | 预计可用 {} 天 {} 小时",
                rate.hourly_rate, days, hours
            )
        }
    }

    fn history_chart(lang: &str, records: &[HistoryRecord]) -> Vec<String> {
        let points: Vec<&HistoryRecord> = records.iter().rev().take(24).collect();
        let points: Vec<&HistoryRecord> = points.into_iter().rev().collect();
        let min_total = points
            .iter()
            .map(|record| record.total)
            .fold(f64::INFINITY, f64::min);
        let max_total = points
            .iter()
            .map(|record| record.total)
            .fold(f64::NEG_INFINITY, f64::max);
        let span = (max_total - min_total).max(0.01);
        let width = 54_usize;
        let height = 10_usize;
        let mut grid = vec![vec![' '; width]; height];
        for (index, record) in points.iter().enumerate() {
            let x = if points.len() == 1 {
                width / 2
            } else {
                index * (width - 1) / (points.len() - 1)
            };
            let y = height
                - 1
                - (((record.total - min_total) / span) * (height - 1) as f64).round() as usize;
            grid[y][x] = '*';
        }
        let mut lines = Vec::new();
        lines.push(format!(
            "Y {}: {}",
            tr(lang, "history_total"),
            format_amount(max_total)
        ));
        for (row_index, row) in grid.into_iter().enumerate() {
            let value = max_total - span * row_index as f64 / (height - 1) as f64;
            let label = if row_index == 0 || row_index == height / 2 || row_index == height - 1 {
                format!("{:>10}", format_amount(value))
            } else {
                " ".repeat(10)
            };
            lines.push(format!("{label} |{}", row.into_iter().collect::<String>()));
        }
        lines.push(format!("{} +{}", " ".repeat(10), "-".repeat(width)));
        if let (Some(first), Some(last)) = (points.first(), points.last()) {
            lines.push(format!("X {} -> {}", first.timestamp, last.timestamp));
        }
        lines
    }

    fn trend_label(lang: &str, value: f64) -> &'static str {
        if value > 0.000001 {
            tr(lang, "history_rising")
        } else if value < -0.000001 {
            tr(lang, "history_falling")
        } else {
            tr(lang, "history_flat")
        }
    }

    fn export_balance_history(
        days: u64,
        currency: Option<&str>,
        export_path: &str,
    ) -> Result<PathBuf, String> {
        let records = history_records(days, currency, usize::MAX)?;
        let path = history_export_file(export_path);
        if let Some(parent) = path.parent() {
            ensure_dir(parent).map_err(|e| e.to_string())?;
        }
        fs::write(&path, history_csv(&records)).map_err(|e| e.to_string())?;
        Ok(path)
    }

    fn history_csv(records: &[HistoryRecord]) -> String {
        let mut lines = vec!["timestamp,currency,total,topped,granted,service_status".to_string()];
        for record in records {
            lines.push(format!(
                "{},{},{},{},{},{}",
                csv_escape(&record.timestamp),
                csv_escape(&record.currency),
                format_amount(record.total),
                format_amount(record.topped),
                format_amount(record.granted),
                csv_escape(&record.service_status)
            ));
        }
        lines.join("\n") + "\n"
    }

    fn csv_escape(value: &str) -> String {
        if value.contains(|ch| ch == ',' || ch == '"' || ch == '\n') {
            format!("\"{}\"", value.replace('"', "\"\""))
        } else {
            value.to_string()
        }
    }

    fn prune_balance_history(retention_days: u64) -> Result<(), String> {
        let conn = open_history_db()?;
        let cutoff = (Local::now() - ChronoDuration::days(retention_days as i64))
            .format("%Y-%m-%d %H:%M:%S")
            .to_string();
        conn.execute(
            "DELETE FROM balance_history WHERE timestamp < ?1",
            params![cutoff],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    fn open_history_db() -> Result<Connection, String> {
        ensure_dir(&config_dir()).map_err(|e| e.to_string())?;
        let path = db_file();
        warn_if_recreating_database(&path);
        let conn = Connection::open(&path).map_err(|e| e.to_string())?;
        conn.busy_timeout(Duration::from_secs(5))
            .map_err(|e| e.to_string())?;
        conn.pragma_update(None, "journal_mode", "WAL")
            .map_err(|e| e.to_string())?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                currency TEXT NOT NULL,
                total REAL NOT NULL,
                topped REAL NOT NULL,
                granted REAL NOT NULL,
                service_status TEXT NOT NULL DEFAULT 'unknown'
            )",
            [],
        )
        .map_err(|e| e.to_string())?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp ON balance_history (timestamp)",
            [],
        )
        .map_err(|e| e.to_string())?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_balance_history_currency_timestamp ON balance_history (currency, timestamp)",
            [],
        )
        .map_err(|e| e.to_string())?;
        ensure_history_service_status_column(&conn)?;
        conn.execute(
            "CREATE TABLE IF NOT EXISTS secure_settings (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                updated_at TEXT NOT NULL
            )",
            [],
        )
        .map_err(|e| e.to_string())?;
        mark_database_initialized().map_err(|e| e.to_string())?;
        Ok(conn)
    }

    fn ensure_history_service_status_column(conn: &Connection) -> Result<(), String> {
        let mut stmt = conn
            .prepare("PRAGMA table_info(balance_history)")
            .map_err(|e| e.to_string())?;
        let columns = stmt
            .query_map([], |row| row.get::<_, String>(1))
            .map_err(|e| e.to_string())?;
        for column in columns {
            if column.map_err(|e| e.to_string())? == "service_status" {
                return Ok(());
            }
        }
        conn.execute(
            "ALTER TABLE balance_history ADD COLUMN service_status TEXT NOT NULL DEFAULT 'unknown'",
            [],
        )
        .map_err(|e| e.to_string())?;
        Ok(())
    }

    fn warn_if_recreating_database(path: &Path) {
        let marker = db_marker_file();
        if marker.exists() && !path.exists() {
            let message = format!(
                "SQLite database is missing: {}. A new database will be created; balance history and API keys stored only in SQLite may be lost.",
                path.display()
            );
            DATABASE_RECREATED_WARNING.store(true, Ordering::SeqCst);
            eprintln!("{message}");
            log_line(&message);
        }
    }

    fn mark_database_initialized() -> std::io::Result<()> {
        let marker = db_marker_file();
        if !marker.exists() {
            fs::write(marker, "1\n")?;
        }
        Ok(())
    }

    fn prune_logs_on_startup(config: &AppConfig) -> std::io::Result<()> {
        ensure_dir(&config_dir())?;
        prune_log_file(&log_file(), config.retention_days)
    }

    fn prune_log_file(path: &Path, retention_days: u64) -> std::io::Result<()> {
        let content = match fs::read_to_string(path) {
            Ok(content) => content,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error),
        };
        let cutoff = Local::now().naive_local() - ChronoDuration::days(retention_days as i64);
        let mut changed = false;
        let mut retained = String::new();
        for line in content.lines() {
            if keep_log_line(line, cutoff) {
                retained.push_str(line);
                retained.push('\n');
            } else {
                changed = true;
            }
        }
        if changed {
            fs::write(path, retained)?;
        }
        Ok(())
    }

    fn keep_log_line(line: &str, cutoff: NaiveDateTime) -> bool {
        let Some(timestamp) = line.strip_prefix('[').and_then(|rest| rest.get(..19)) else {
            return true;
        };
        NaiveDateTime::parse_from_str(timestamp, "%Y-%m-%d %H:%M:%S")
            .map(|logged_at| logged_at >= cutoff)
            .unwrap_or(true)
    }

    fn set_auto_start(enable: bool) -> Result<(), String> {
        if enable {
            create_startup_shortcut()
        } else {
            match fs::remove_file(startup_shortcut_path()?) {
                Ok(()) => Ok(()),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
                Err(error) => Err(error.to_string()),
            }
        }
    }

    fn create_startup_shortcut() -> Result<(), String> {
        let _com = init_com()?;
        let exe = std::env::current_exe().map_err(|e| e.to_string())?;
        let link_path = startup_shortcut_path()?;
        if let Some(parent) = link_path.parent() {
            ensure_dir(parent).map_err(|e| e.to_string())?;
        }

        let mut raw_link = ptr::null_mut();
        // SAFETY: CoCreateInstance writes a COM interface pointer for the ShellLink class.
        let hr = unsafe {
            CoCreateInstance(
                &CLSID_SHELL_LINK,
                ptr::null_mut(),
                CLSCTX_INPROC_SERVER,
                &IID_ISHELL_LINK_W,
                &mut raw_link,
            )
        };
        check_hr(hr, "CoCreateInstance")?;
        let link = ShellLinkPtr(raw_link as *mut IShellLinkW);

        let exe_w = wide_null(exe.as_os_str());
        let description_w = wide_null(OsStr::new(APP_NAME));
        // SAFETY: ShellLink pointer and UTF-16 strings are valid for each call.
        unsafe {
            check_hr(
                ((*(*link.0).lp_vtbl).set_path)(link.0, exe_w.as_ptr()),
                "SetPath",
            )?;
            check_hr(
                ((*(*link.0).lp_vtbl).set_description)(link.0, description_w.as_ptr()),
                "SetDescription",
            )?;
            check_hr(
                ((*(*link.0).lp_vtbl).set_icon_location)(link.0, exe_w.as_ptr(), 0),
                "SetIconLocation",
            )?;
            if let Some(parent) = exe.parent() {
                let work_dir_w = wide_null(parent.as_os_str());
                check_hr(
                    ((*(*link.0).lp_vtbl).set_working_directory)(link.0, work_dir_w.as_ptr()),
                    "SetWorkingDirectory",
                )?;
            }
        }

        let mut raw_persist = ptr::null_mut();
        // SAFETY: QueryInterface writes an IPersistFile pointer for the same COM object.
        let hr = unsafe {
            ((*(*link.0).lp_vtbl).query_interface)(link.0, &IID_IPERSIST_FILE, &mut raw_persist)
        };
        check_hr(hr, "QueryInterface(IPersistFile)")?;
        let persist = PersistFilePtr(raw_persist as *mut IPersistFile);
        let link_path_w = wide_null(link_path.as_os_str());
        // SAFETY: IPersistFile pointer is valid and link_path_w is null-terminated.
        let hr = unsafe { ((*(*persist.0).lp_vtbl).save)(persist.0, link_path_w.as_ptr(), 1) };
        check_hr(hr, "IPersistFile::Save")
    }

    fn startup_shortcut_path() -> Result<PathBuf, String> {
        Ok(startup_folder()?.join(STARTUP_LINK_NAME))
    }

    fn startup_folder() -> Result<PathBuf, String> {
        let mut buffer = [0u16; 260];
        // SAFETY: buffer is a writable MAX_PATH-sized UTF-16 buffer for SHGetFolderPathW.
        let hr = unsafe {
            SHGetFolderPathW(
                ptr::null_mut(),
                CSIDL_STARTUP | CSIDL_FLAG_CREATE,
                ptr::null_mut(),
                0,
                buffer.as_mut_ptr(),
            )
        };
        check_hr(hr, "SHGetFolderPathW(CSIDL_STARTUP)")?;
        let len = buffer
            .iter()
            .position(|&ch| ch == 0)
            .unwrap_or(buffer.len());
        Ok(PathBuf::from(OsString::from_wide(&buffer[..len])))
    }

    fn init_com() -> Result<ComApartment, String> {
        // SAFETY: Initializes COM for the current thread before using ShellLink COM APIs.
        let hr = unsafe { CoInitializeEx(ptr::null_mut(), COINIT_APARTMENTTHREADED) };
        if hr >= 0 {
            Ok(ComApartment { uninitialize: true })
        } else if hr == RPC_E_CHANGED_MODE {
            Ok(ComApartment {
                uninitialize: false,
            })
        } else {
            Err(format_hresult("CoInitializeEx", hr))
        }
    }

    fn acquire_single_instance_lock() -> Result<(), String> {
        let name = wide_null(OsStr::new(SINGLE_INSTANCE_MUTEX));
        // SAFETY: name is a null-terminated UTF-16 string. The returned handle is
        // intentionally never closed so the mutex is held for the whole process.
        let handle = unsafe { CreateMutexW(ptr::null_mut(), 0, name.as_ptr()) };
        if handle.is_null() {
            return Err("Failed to create single-instance mutex".to_string());
        }
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            return Err("DeepSeek Balance Monitor is already running.".to_string());
        }
        Ok(())
    }

    fn show_already_running_message() {
        let text = wide_null(OsStr::new(
            "DeepSeek Balance Monitor is already running.\nDeepSeek 余额监控已在运行。",
        ));
        let caption = wide_null(OsStr::new(APP_NAME));
        // SAFETY: text and caption are null-terminated UTF-16 strings.
        unsafe {
            MessageBoxW(ptr::null_mut(), text.as_ptr(), caption.as_ptr(), 0x40);
        }
    }

    fn wide_null(text: &OsStr) -> Vec<u16> {
        text.encode_wide().chain(Some(0)).collect()
    }

    fn check_hr(hr: i32, context: &str) -> Result<(), String> {
        if hr >= 0 {
            Ok(())
        } else {
            Err(format_hresult(context, hr))
        }
    }

    fn format_hresult(context: &str, hr: i32) -> String {
        format!("{context} failed with HRESULT 0x{:08X}", hr as u32)
    }

    fn path_text(path: &Path) -> String {
        path.to_string_lossy().to_string()
    }

    fn tr(lang: &str, key: &str) -> &'static str {
        match (lang, key) {
            ("en", "checking") => "Checking...",
            ("en", "error") => "Error",
            ("en", "view_balance") => "View Balance",
            ("en", "check_now") => "Check Now",
            ("en", "top_up") => "Top Up",
            ("en", "settings") => "Settings...",
            ("en", "quit") => "Quit",
            ("en", "settings_title") => "⚙️ Settings",
            ("en", "account_tab") => "Account",
            ("en", "settings_tab") => "Settings",
            ("en", "history_tab") => "History",
            ("en", "group_credentials") => "Credentials",
            ("en", "group_query") => "Query",
            ("en", "group_general") => "General",
            ("en", "group_proxy") => "Proxy",
            ("en", "group_appearance") => "Icon Appearance",
            ("en", "api_key_label") => "DeepSeek API Key:",
            ("en", "show_key") => "Show API Key",
            ("en", "interval_label") => "Check interval (minutes, 1-1440):",
            ("en", "threshold_label") => "Low balance threshold:",
            ("en", "language_label") => "Language:",
            ("en", "auto_start") => "Auto-start on boot",
            ("en", "alert_mode_label") => "Low Balance Alert:",
            ("en", "alert_mode_never") => "Never",
            ("en", "alert_mode_always") => "Always",
            ("en", "alert_mode_once") => "Once",
            ("en", "api_alert_label") => "API service status alerts",
            ("en", "retention_label") => "Log & record retention (days):",
            ("en", "export_path_label") => "Export path:",
            ("en", "proxy_label") => "HTTP/HTTPS proxy:",
            ("en", "proxy_enable") => "Enable HTTP/HTTPS proxy",
            ("en", "proxy_placeholder") => "Proxy address",
            ("en", "theme_label") => "Icon theme:",
            ("en", "theme_default") => "Default",
            ("en", "theme_contrast") => "High Contrast",
            ("en", "theme_bright") => "Bright",
            ("en", "theme_dark_mode") => "Dark Mode",
            ("en", "theme_mono") => "Monochrome",
            ("en", "theme_custom") => "Custom",
            ("en", "icon_stroke_label") => "Icon stroke",
            ("en", "custom_colors_label") => "Custom colors: OK / Low / Degraded / No data",
            ("en", "color_hex_error") => "Custom colors must be 6-digit hex values.",
            ("en", "save") => "Save",
            ("en", "cancel") => "Cancel",
            ("en", "refresh") => "Refresh",
            ("en", "export") => "Export",
            ("en", "export_success") => "Exported:",
            ("en", "export_failed") => "Export failed:",
            ("en", "history_days") => "Days",
            ("en", "history_currency_filter") => "Currency",
            ("en", "history_all") => "All",
            ("en", "history_chart") => "Trend",
            ("en", "history_page") => "Page",
            ("en", "history_trend") => "Trend",
            ("en", "history_rising") => "Rising",
            ("en", "history_falling") => "Falling",
            ("en", "history_flat") => "Flat",
            ("en", "history_range") => "Range",
            ("en", "history_avg") => "Average",
            ("en", "history_change") => "Change",
            ("en", "daily_rate") => "Avg",
            ("en", "estimated_remaining") => "Est.",
            ("en", "not_enough_data") => "Not enough data",
            ("en", "prev_page") => "Previous",
            ("en", "next_page") => "Next",
            ("en", "api_key_empty") => "API Key is required.",
            ("en", "interval_number") => "Check interval must be a number.",
            ("en", "interval_range") => "Check interval must be between 1 and 1440 minutes.",
            ("en", "threshold_number") => "Low balance threshold must be a number.",
            ("en", "threshold_range") => "Low balance threshold must be between 0 and 10000.",
            ("en", "retention_number") => "Retention days must be a number.",
            ("en", "retention_range") => "Retention days must be between 1 and 3650.",
            ("en", "not_checked") => "Not checked",
            ("en", "total_balance") => "Total balance",
            ("en", "topped_up") => "Topped",
            ("en", "granted") => "Granted",
            ("en", "last_check") => "Last check",
            ("en", "history_empty") => "No balance history.",
            ("en", "history_time") => "Time",
            ("en", "history_currency") => "Currency",
            ("en", "history_total") => "Total",
            ("en", "balance_title") => "DeepSeek Balance",
            ("en", "bal_title") => "DeepSeek Balance:",
            ("en", "query_error") => "Query error",
            ("en", "service_status") => "DeepSeek API Status:",
            ("en", "status_none") => "All Systems Operational",
            ("en", "status_minor") => "Minor Outage",
            ("en", "status_major") => "Major Outage",
            ("en", "status_critical") => "Critical Outage",
            ("en", "status_maintenance") => "Under Maintenance",
            ("en", "status_unknown") => "Status Unknown",
            ("en", "balance_empty") => {
                "No balance data yet. Click Check Now or wait for the next check."
            }
            ("en", "balance_error_title") => "DeepSeek Balance - Error",
            ("en", "low_balance_title") => "DeepSeek Low Balance",
            ("en", "low_balance_body") => "Balance is only",
            ("en", "threshold") => "threshold",
            ("en", "api_key_missing_title") => "DeepSeek API Key required",
            ("en", "api_key_missing_body") => {
                "Open Settings and enter your API key. It is encrypted locally and is not sent to the developer."
            }
            ("en", "database_recreated_title") => "DeepSeek database recreated",
            ("en", "database_recreated_body") => {
                "The SQLite database was missing and has been recreated. Balance history and API keys stored only in SQLite may be lost."
            }
            ("en", "api_degraded_title") => "⚠ DeepSeek API Degraded",
            ("en", "api_degraded_msg") => "API service status has changed: ",
            ("en", "api_recovered_title") => "✅ DeepSeek API Recovered",
            ("en", "api_recovered_msg") => "API service is back to normal.",
            ("en", "subscription_tab") => "Subscriptions",
            ("en", "og_title") => "OpenCode Go",
            ("en", "og_api_key_label") => "OpenCode Go API key:",
            ("en", "og_show_api_key") => "Show API key",
            ("en", "og_hint") => "Get an API key from https://opencode.ai/auth and enter it above. The key is encrypted and stored locally.",
            ("en", "og_refresh") => "Refresh",
            ("en", "og_window_5h") => "5h",
            ("en", "og_window_weekly") => "Weekly",
            ("en", "og_window_monthly") => "Monthly",
            ("en", "og_unavailable") => "unavailable",
            ("en", "og_checking") => "Checking...",
            ("en", "og_not_configured") => "OpenCode Go API key is not configured. Add it on the Account tab.",
            ("en", "og_credentials_saved") => "Credentials saved.",
            ("en", "og_refresh_failed") => "Refresh failed:",
            ("en", "og_loaded") => "Loaded.",
            ("en", "og_api_key_hint") => "Leave blank to keep the existing API key.",
            ("en", "group_og") => "OpenCode Go",
            ("en", "group_cc") => "Command Code",
            ("en", "cc_api_key_label") => "Command Code API key:",
            ("en", "cc_show_api_key") => "Show API key",
            ("en", "cc_hint") => "Get an API key from https://commandcode.ai and enter it above. The key is encrypted and stored locally.",
            ("en", "cc_refresh") => "Refresh",
            ("en", "cc_window_5h") => "5h",
            ("en", "cc_window_weekly") => "Weekly",
            ("en", "cc_window_monthly") => "Monthly",
            ("en", "cc_unavailable") => "unavailable",
            ("en", "cc_checking") => "Checking...",
            ("en", "cc_not_configured") => "Command Code API key is not configured. Add it on the Account tab.",
            ("en", "cc_refresh_failed") => "Refresh failed:",
            ("en", "cc_loaded") => "Loaded.",
            ("en", "cc_api_key_hint") => "Leave blank to keep the existing API key.",
            ("en", "warn_title") => "Warning",
            (_, "checking") => "查询中...",
            (_, "error") => "错误",
            (_, "view_balance") => "查看余额",
            (_, "check_now") => "立即查询",
            (_, "top_up") => "充值",
            (_, "settings") => "设置...",
            (_, "quit") => "退出",
            (_, "settings_title") => "⚙️ 设置",
            (_, "account_tab") => "账户",
            (_, "settings_tab") => "设置",
            (_, "history_tab") => "历史",
            (_, "group_credentials") => "凭据",
            (_, "group_query") => "查询",
            (_, "group_general") => "通用",
            (_, "group_proxy") => "代理",
            (_, "group_appearance") => "图标外观",
            (_, "api_key_label") => "DeepSeek API Key:",
            (_, "show_key") => "显示 API Key",
            (_, "interval_label") => "查询间隔（分钟，1-1440）：",
            (_, "threshold_label") => "余额预警线：",
            (_, "language_label") => "语言 / Language:",
            (_, "auto_start") => "开机自动启动",
            (_, "alert_mode_label") => "低余额提醒：",
            (_, "alert_mode_never") => "不提醒",
            (_, "alert_mode_always") => "持续提醒",
            (_, "alert_mode_once") => "仅提醒一次",
            (_, "api_alert_label") => "API 服务状态变化提醒",
            (_, "retention_label") => "日志和记录保留天数：",
            (_, "export_path_label") => "数据导出路径：",
            (_, "proxy_label") => "HTTP/HTTPS 代理：",
            (_, "proxy_enable") => "启用 HTTP/HTTPS 代理",
            (_, "proxy_placeholder") => "代理地址",
            (_, "theme_label") => "图标主题：",
            (_, "theme_default") => "默认",
            (_, "theme_contrast") => "高对比",
            (_, "theme_bright") => "明亮",
            (_, "theme_dark_mode") => "暗色模式",
            (_, "theme_mono") => "纯灰度",
            (_, "theme_custom") => "自定义",
            (_, "icon_stroke_label") => "图标描边",
            (_, "custom_colors_label") => "自定义颜色：正常 / 低额 / 异常 / 无数据",
            (_, "color_hex_error") => "自定义颜色必须是 6 位 hex 值。",
            (_, "save") => "保存",
            (_, "cancel") => "取消",
            (_, "refresh") => "刷新",
            (_, "export") => "导出",
            (_, "export_success") => "已导出：",
            (_, "export_failed") => "导出失败：",
            (_, "history_days") => "天数",
            (_, "history_currency_filter") => "币种",
            (_, "history_all") => "全部",
            (_, "history_chart") => "趋势图",
            (_, "history_page") => "第",
            (_, "history_trend") => "趋势",
            (_, "history_rising") => "上升",
            (_, "history_falling") => "下降",
            (_, "history_flat") => "持平",
            (_, "history_range") => "范围",
            (_, "history_avg") => "平均",
            (_, "history_change") => "变化",
            (_, "daily_rate") => "日均消耗",
            (_, "estimated_remaining") => "预计可用",
            (_, "not_enough_data") => "数据不足，无法计算",
            (_, "prev_page") => "上一页",
            (_, "next_page") => "下一页",
            (_, "api_key_empty") => "API Key 不能为空。",
            (_, "interval_number") => "查询间隔必须是数字。",
            (_, "interval_range") => "查询间隔必须在 1 到 1440 分钟之间。",
            (_, "threshold_number") => "余额预警线必须是数字。",
            (_, "threshold_range") => "余额预警线必须在 0 到 10000 之间。",
            (_, "retention_number") => "保留天数必须是数字。",
            (_, "retention_range") => "保留天数必须在 1 到 3650 天之间。",
            (_, "not_checked") => "尚未查询",
            (_, "total_balance") => "总余额",
            (_, "topped_up") => "充值",
            (_, "granted") => "赠送",
            (_, "last_check") => "上次查询",
            (_, "history_empty") => "暂无余额历史。",
            (_, "history_time") => "时间",
            (_, "history_currency") => "币种",
            (_, "history_total") => "总余额",
            (_, "balance_title") => "DeepSeek 余额",
            (_, "bal_title") => "DeepSeek 余额：",
            (_, "query_error") => "查询出错",
            (_, "service_status") => "DeepSeek API 服务状态：",
            (_, "status_none") => "服务正常",
            (_, "status_minor") => "轻微异常",
            (_, "status_major") => "严重异常",
            (_, "status_critical") => "关键不可用",
            (_, "status_maintenance") => "维护中",
            (_, "status_unknown") => "服务状态未知",
            (_, "balance_empty") => "尚未查询到余额，请稍后或点击立即查询。",
            (_, "balance_error_title") => "DeepSeek 余额 - 错误",
            (_, "low_balance_title") => "DeepSeek 余额不足",
            (_, "low_balance_body") => "当前余额仅剩",
            (_, "threshold") => "预警线",
            (_, "api_key_missing_title") => "请输入 DeepSeek API Key",
            (_, "api_key_missing_body") => {
                "请打开设置填写 API Key。它会在本机加密保存，开发者不会获取。"
            }
            (_, "database_recreated_title") => "DeepSeek 数据库已重建",
            (_, "database_recreated_body") => {
                "SQLite 数据库文件缺失，已自动重建。历史记录以及仅存于 SQLite 的 API Key 可能已丢失。"
            }
            (_, "api_degraded_title") => "⚠ DeepSeek API 服务异常",
            (_, "api_degraded_msg") => "检测到 API 服务状态异常：",
            (_, "api_recovered_title") => "✅ DeepSeek API 服务恢复",
            (_, "api_recovered_msg") => "API 服务已恢复正常。",
            (_, "subscription_tab") => "订阅",
            (_, "og_title") => "OpenCode Go",
            (_, "og_api_key_label") => "OpenCode Go API Key：",
            (_, "og_show_api_key") => "显示 API Key",
            (_, "og_hint") => "API Key 可在 https://opencode.ai/auth 获取并填入上方。密钥将加密存储在本机。",
            (_, "og_refresh") => "刷新",
            (_, "og_window_5h") => "5h",
            (_, "og_window_weekly") => "每周",
            (_, "og_window_monthly") => "每月",
            (_, "og_unavailable") => "不可用",
            (_, "og_checking") => "查询中...",
            (_, "og_not_configured") => "尚未配置 OpenCode Go API Key。请在「账户」标签页配置。",
            (_, "og_credentials_saved") => "凭据已保存。",
            (_, "og_refresh_failed") => "刷新失败：",
            (_, "og_loaded") => "已加载。",
            (_, "og_api_key_hint") => "留空则保留现有 API Key。",
            (_, "group_og") => "OpenCode Go",
            (_, "group_cc") => "Command Code",
            (_, "cc_api_key_label") => "Command Code API Key：",
            (_, "cc_show_api_key") => "显示 API Key",
            (_, "cc_hint") => "API Key 可在 https://commandcode.ai 获取并填入上方。密钥将加密存储在本机。",
            (_, "cc_refresh") => "刷新",
            (_, "cc_window_5h") => "5h",
            (_, "cc_window_weekly") => "每周",
            (_, "cc_window_monthly") => "每月",
            (_, "cc_unavailable") => "不可用",
            (_, "cc_checking") => "查询中...",
            (_, "cc_not_configured") => "尚未配置 Command Code API Key。请在「账户」标签页配置。",
            (_, "cc_refresh_failed") => "刷新失败：",
            (_, "cc_loaded") => "已加载。",
            (_, "cc_api_key_hint") => "留空则保留现有 API Key。",
            (_, "warn_title") => "警告",
            _ => "",
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        fn balance(total: f64) -> Balance {
            Balance {
                total_balance: total,
                granted_balance: 1.0,
                topped_up_balance: total - 1.0,
            }
        }

        #[test]
        fn formats_status_icon_labels_and_low_balance_alerts() {
            assert_eq!(parse_amount("12.34"), 12.34);
            assert_eq!(parse_amount("bad"), 0.0);
            assert_eq!(format_amount(1.2), "1.20");
            assert_eq!(format_signed_amount(-2.0), "-2.00");
            assert_eq!(normalize_service_status("partial_outage"), "major");
            assert!(status_rank("critical") > status_rank("major"));
            assert!(service_degraded("minor"));
            assert_eq!(AppConfig::default().language, "en");
            assert_eq!(icon_label(99.9), "99");
            assert_eq!(icon_label(100.0), "OK");
            let now = Local::now();
            assert_eq!(
                relative_time("zh", now - ChronoDuration::minutes(5), now),
                "5 分钟前"
            );
            assert!(demo::is_enabled(" demo "));
            let conn = Connection::open_in_memory().expect("in-memory sqlite opens");
            demo::prepare(&conn).expect("demo table prepares");
            let demo = demo::balances(&conn).expect("demo balances load");
            let demo_balance = demo.get("CNY").expect("demo balance exists");
            assert_eq!(demo_balance.total_balance, 666.0);
            assert_eq!(demo_balance.topped_up_balance, 114_514.0);
            assert_eq!(demo_balance.granted_balance, 1_919_810.0);
            assert_eq!(
                demo::consumption_rate(&conn)
                    .expect("demo rate loads")
                    .hourly_rate,
                114_514.0
            );
            assert!(demo::history(&conn, 24).expect("demo history loads").len() > 1);

            let mut state = RuntimeState::default();
            state.config.threshold_yuan = 10.0;
            state.balances.insert("CNY".to_string(), balance(5.0));
            let rate = ConsumptionRate {
                hourly_rate: 1.5,
                busy_hours_left: 28.0 * 24.0 + 4.0,
                currency: "CNY".to_string(),
            };
            let message = balance_notification_message(
                "zh",
                &state.balances,
                Some(&rate),
                None,
                Some(now - ChronoDuration::minutes(5)),
                "none",
                now,
            );
            assert!(message.contains("💰 5.00 CNY"));
            assert!(message.contains("📊 忙时消耗 1.50/小时 | 预计可用 28 天 4 小时"));
            assert!(message.contains("📡 DeepSeek API 服务状态：🟢 服务正常"));
            assert!(message.contains("🕐 上次查询：5 分钟前"));
            let snapshot = RainmeterSnapshot {
                config: state.config.clone(),
                balances: state.balances.clone(),
                last_check: Some(now - ChronoDuration::minutes(5)),
                error: None,
                checking: false,
                service_status: "none".to_string(),
                opencode_configured: true,
                opencode: Some(OpenCodeGoQuota {
                    rolling: Some(OpenCodeGoUsage {
                        usage_percent: 42.0,
                        percent_remaining: 58.0,
                        reset_in_sec: 6960,
                    }),
                    weekly: None,
                    monthly: Some(OpenCodeGoUsage {
                        usage_percent: 30.0,
                        percent_remaining: 70.0,
                        reset_in_sec: 1_548_000,
                    }),
                }),
                opencode_error: None,
                command_code_configured: true,
                command_code: Some(CommandCodeQuota {
                    five_hour: Some(CommandCodeWindow {
                        used: 4.2,
                        cap: 14.0,
                        reset_in_sec: 6960,
                    }),
                    weekly: None,
                    monthly: Some(CommandCodeWindow {
                        used: 22.0,
                        cap: GOAT_MONTHLY_CREDITS,
                        reset_in_sec: 1_548_000,
                    }),
                }),
                command_code_error: None,
            };
            let rainmeter_json = rainmeter_status_json(&snapshot, Some(&rate), "zh", now);
            let rainmeter: serde_json::Value =
                serde_json::from_str(&rainmeter_json).expect("rainmeter json parses");
            assert_eq!(rainmeter["accent_color"].as_str(), Some("185,70,60"));
            assert_eq!(rainmeter["balance_line"].as_str(), Some("💰 5.00 CNY"));
            assert_eq!(rainmeter["last_check"].as_str(), Some("5 分钟前"));
            assert_eq!(
                rainmeter["service_status_line"].as_str(),
                Some("🟢 服务正常")
            );
            assert_eq!(
                rainmeter["estimated_line"].as_str(),
                Some("📊 忙时消耗 1.50/小时 | 预计可用 28 天 4 小时")
            );
            assert_eq!(rainmeter["og_configured"].as_bool(), Some(true));
            assert_eq!(rainmeter["og_rolling_percent"].as_i64(), Some(42));
            assert_eq!(rainmeter["og_rolling_line"].as_str(), Some("42% · 1h 56m"));
            assert_eq!(rainmeter["og_weekly_line"].as_str(), Some("不可用"));
            assert_eq!(rainmeter["og_monthly_percent"].as_i64(), Some(30));
            assert_eq!(rainmeter["og_monthly_line"].as_str(), Some("30% · 17d 22h"));
            assert_eq!(rainmeter["cc_configured"].as_bool(), Some(true));
            assert_eq!(rainmeter["cc_5h_percent"].as_i64(), Some(30));
            assert_eq!(rainmeter["cc_5h_line"].as_str(), Some("4.2/14.0 · 1h 56m"));
            assert_eq!(rainmeter["cc_weekly_line"].as_str(), Some("不可用"));
            assert_eq!(rainmeter["cc_monthly_percent"].as_i64(), Some(31));
            assert_eq!(
                rainmeter["cc_monthly_line"].as_str(),
                Some("22.0/70.0 · 17d 22h")
            );
            assert_eq!(request_language("/widget-status?lang=en", "zh"), "en");
            assert!(is_low_balance(&state));
            assert!(should_low_balance_alert(&mut state, true));
            assert!(!should_low_balance_alert(&mut state, true));
            assert!(!should_low_balance_alert(&mut state, false));
            assert!(should_low_balance_alert(&mut state, true));
            state.config.alert_mode = "never".to_string();
            assert!(!should_low_balance_alert(&mut state, true));
            state.config.alert_mode = "always".to_string();
            assert!(should_low_balance_alert(&mut state, true));
        }

        #[test]
        fn keeps_shared_theme_config_contracts() {
            let colors = parse_icon_colors([
                "#3c6966".to_string(),
                "b9463c".to_string(),
                "78695a".to_string(),
                "69696e".to_string(),
            ])
            .unwrap();
            assert_eq!(colors.get("ok").map(String::as_str), Some("3c6966"));
            assert!(parse_icon_colors([
                "bad".to_string(),
                "b9463c".to_string(),
                "78695a".to_string(),
                "69696e".to_string(),
            ])
            .is_err());

            let mut config = AppConfig::default();
            assert_eq!(theme_color(&config, "ok").0, [60, 105, 102, 255]);
            config.theme = "contrast".to_string();
            assert_eq!(theme_color(&config, "low").0, [212, 52, 46, 255]);
            config.theme = "custom".to_string();
            config.icon_colors = colors;
            assert_eq!(theme_color(&config, "degraded").0, [120, 105, 90, 255]);
            assert_eq!(
                custom_or_default_colors(&AppConfig::default()).get("nodata"),
                Some(&"69696e".to_string())
            );
        }

        #[test]
        fn summarizes_history_csv_and_log_retention() {
            let records = vec![
                HistoryRecord {
                    timestamp: "2026-01-01 00:00:00".to_string(),
                    currency: "CNY".to_string(),
                    total: 10.0,
                    topped: 8.0,
                    granted: 2.0,
                    service_status: "none".to_string(),
                },
                HistoryRecord {
                    timestamp: "2026-01-02 00:00:00".to_string(),
                    currency: "CNY".to_string(),
                    total: 7.0,
                    topped: 5.0,
                    granted: 2.0,
                    service_status: "minor".to_string(),
                },
            ];
            let summary = summarize_history(&records);
            assert_eq!(summary[0].records, 2);
            assert_eq!(summary[0].latest_total, 7.0);
            assert_eq!(summary[0].change_total, -3.0);
            assert!(history_csv(&records).contains("2026-01-02 00:00:00,CNY,7.00,5.00,2.00,minor"));
            assert_eq!(csv_escape("CNY,\"test\""), "\"CNY,\"\"test\"\"\"");
            assert_eq!(
                history_export_file(r"C:\dsbm-export").parent().unwrap(),
                Path::new(r"C:\dsbm-export")
            );
            assert_eq!(
                history_export_file("")
                    .file_name()
                    .unwrap()
                    .to_string_lossy(),
                history_export_filename()
            );

            let cutoff =
                NaiveDateTime::parse_from_str("2026-01-02 00:00:00", "%Y-%m-%d %H:%M:%S").unwrap();
            assert!(!keep_log_line("[2026-01-01 23:59:59] old", cutoff));
            assert!(keep_log_line("[2026-01-02 00:00:00] keep", cutoff));
            assert!(keep_log_line("unstructured line", cutoff));
        }

        #[test]
        fn parses_opencode_go_api_json() {
            // 模拟 /zen/go/v1/usage 的真实响应
            let payload = r#"{
                "usage": {
                    "rolling": {"status": "ok", "percent": 42.5, "resetsAt": "2026-01-02T00:00:00Z"},
                    "weekly": {"status": "ok", "percent": 80, "resetsAt": "2026-01-08T00:00:00Z"},
                    "monthly": {"status": "ok", "percent": 15, "resetsAt": "2026-01-01T00:00:00Z"}
                }
            }"#;
            let parsed: OpenCodeGoApiResponse =
                serde_json::from_str(payload).expect("API response parses");
            let now = 1_767_225_600; // 2026-01-01T00:00:00Z
            let quota = OpenCodeGoQuota {
                rolling: parsed
                    .usage
                    .rolling
                    .map(|window| api_window_to_usage(window, now)),
                weekly: parsed
                    .usage
                    .weekly
                    .map(|window| api_window_to_usage(window, now)),
                monthly: parsed
                    .usage
                    .monthly
                    .map(|window| api_window_to_usage(window, now)),
            };
            let rolling = quota.rolling.expect("rolling window");
            assert_eq!(rolling.usage_percent, 42.5);
            assert_eq!(rolling.reset_in_sec, 86400);
            assert!((rolling.percent_remaining - 57.5).abs() < 1e-9);
            let weekly = quota.weekly.expect("weekly window");
            assert_eq!(weekly.usage_percent, 80.0);
            assert_eq!(weekly.reset_in_sec, 7 * 86400);
            let monthly = quota.monthly.expect("monthly window");
            assert_eq!(monthly.usage_percent, 15.0);
            assert_eq!(monthly.reset_in_sec, 0);

            // 部分响应只含 rolling 窗口
            let partial =
                r#"{"usage": {"rolling": {"percent": 10, "resetsAt": "2026-01-01T00:00:00Z"}}}"#;
            let parsed: OpenCodeGoApiResponse =
                serde_json::from_str(partial).expect("partial API response parses");
            assert!(parsed.usage.rolling.is_some());
            assert!(parsed.usage.weekly.is_none());
            assert!(parsed.usage.monthly.is_none());

            // 错误响应 message 提取
            let error_body =
                r#"{"type":"error","error":{"type":"AuthError","message":"Invalid API key."}}"#;
            assert_eq!(
                parse_opencode_go_api_error(error_body).as_deref(),
                Some("Invalid API key.")
            );
            assert_eq!(parse_opencode_go_api_error("not json"), None);

            // 显示格式保留
            assert_eq!(format_reset_seconds(0), "now");
            assert_eq!(format_reset_seconds(6960), "1h 56m");
        }

        #[test]
        fn parses_command_code_api_json() {
            // 模拟 /alpha/billing/credits 的真实响应
            let payload = r#"{
                "credits": {
                    "planId": "individual-goat-monthly",
                    "monthlyCredits": 48,
                    "purchasedCredits": 2.5,
                    "freeCredits": 1.5
                },
                "windowLimits": {
                    "limited": true,
                    "fiveHour": {"used": 4.2, "cap": 14, "resetAt": 1798761600000},
                    "weekly": {"used": "17.5", "cap": 35, "resetAt": 1799020800}
                }
            }"#;
            let parsed: CommandCodeApiResponse =
                serde_json::from_str(payload).expect("API response parses");
            let now = 1_767_225_600; // 2026-01-01T00:00:00Z
            let quota = CommandCodeQuota {
                five_hour: parsed
                    .window_limits
                    .five_hour
                    .map(|window| api_cc_window_to_window(window, now)),
                weekly: parsed
                    .window_limits
                    .weekly
                    .map(|window| api_cc_window_to_window(window, now)),
                monthly: command_code_monthly_window(
                    parsed.credits.plan_id.as_deref(),
                    parsed.credits.monthly_credits,
                ),
            };
            let five_hour = quota.five_hour.expect("five hour window");
            assert_eq!(five_hour.used, 4.2);
            assert_eq!(five_hour.cap, 14.0);
            assert!(five_hour.reset_in_sec > 0);
            let weekly = quota.weekly.expect("weekly window");
            assert_eq!(weekly.used, 17.5);
            assert_eq!(weekly.cap, 35.0);
            let monthly = quota.monthly.expect("goat monthly window");
            assert_eq!(monthly.cap, GOAT_MONTHLY_CREDITS);
            assert!((monthly.used - 22.0).abs() < 1e-9);
            assert_eq!(monthly.reset_in_sec, 0);

            // 非 GOAT 套餐不推算月度上限
            let non_goat = r#"{
                "credits": {"planId": "individual-pro-monthly", "monthlyCredits": 12},
                "windowLimits": {"fiveHour": {"used": 1.0, "cap": 10, "resetAt": 0}}
            }"#;
            let parsed: CommandCodeApiResponse =
                serde_json::from_str(non_goat).expect("non-goat API response parses");
            let monthly = command_code_monthly_window(
                parsed.credits.plan_id.as_deref(),
                parsed.credits.monthly_credits,
            );
            assert!(monthly.is_none());

            // 毫秒/秒时间戳归一化
            assert_eq!(
                epoch_to_reset_seconds(Some(1_767_225_600.0), 1_767_225_600),
                0
            );
            assert_eq!(
                epoch_to_reset_seconds(Some(1_767_225_600_000.0), 1_767_225_600),
                0
            );
            assert_eq!(
                epoch_to_reset_seconds(Some(1_767_225_600.0 + 3600.0), 1_767_225_600),
                3600
            );
        }
    }
}

#[cfg(windows)]
fn main() {
    if let Err(error) = windows_app::run() {
        eprintln!("{error}");
    }
}

#[cfg(not(windows))]
fn main() {
    println!("This crate builds the Windows tray app. Use target x86_64-pc-windows-msvc.");
}
