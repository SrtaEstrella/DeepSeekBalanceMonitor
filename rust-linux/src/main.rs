use chrono::{DateTime, Duration as ChronoDuration, Local, NaiveDateTime};
use reqwest::{Proxy, StatusCode};
use ring::aead::{Aad, LessSafeKey, Nonce, UnboundKey, AES_256_GCM};
use ring::rand::{SecureRandom, SystemRandom};
use rusqlite::{params, Connection, Error as SqlError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::os::unix::fs::OpenOptionsExt;
use std::path::{Path, PathBuf};
use std::process;
use std::thread;
use std::time::Duration;

mod demo;

const APP_DIR: &str = "deepseek-balance-monitor";
const HISTORY_DEDUP_SECONDS: i64 = 120;
const SECURE_PREFIX: &[u8] = b"DSBM1";
const SECURE_AAD: &[u8] = b"deepseek-balance-monitor secure_settings api_key v1";
const NONCE_LEN: usize = 12;
const API_KEY_MASK: &str = "masked";
const OPENCODE_GO_API_URL: &str = "https://opencode.ai/zen/go/v1/usage";
const OPENCODE_GO_API_KEY: &str = "opencode_go_api_key";
const COMMAND_CODE_API_BASE: &str = "https://api.commandcode.ai/";
const COMMAND_CODE_API_KEY: &str = "command_code_api_key";

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
    #[serde(default)]
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
            auto_start: false,
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

#[derive(Debug, Serialize)]
struct Balance {
    total_balance: f64,
    granted_balance: f64,
    topped_up_balance: f64,
}

#[derive(Clone, Serialize)]
struct HistoryRecord {
    timestamp: String,
    currency: String,
    total: f64,
    topped: f64,
    granted: f64,
    service_status: String,
}

#[derive(Serialize)]
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

#[derive(Serialize)]
struct HistoryReport {
    days: u64,
    currency: String,
    currencies: Vec<String>,
    total_records: usize,
    summary: Vec<HistorySummary>,
    consumption_rate: Option<ConsumptionRate>,
    records: Vec<HistoryRecord>,
}

#[derive(Clone, Serialize)]
struct ConsumptionRate {
    hourly_rate: f64,
    busy_hours_left: f64,
    currency: String,
}

#[derive(Clone, Debug, Serialize)]
struct OpenCodeGoUsage {
    usage_percent: f64,
    percent_remaining: f64,
    reset_in_sec: i64,
}

#[derive(Clone, Debug, Default, Serialize)]
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

#[derive(Clone, Debug, Default, Serialize)]
struct CommandCodeQuota {
    five_hour: Option<CommandCodeWindow>,
    weekly: Option<CommandCodeWindow>,
    monthly: Option<CommandCodeWindow>,
}

#[derive(Clone, Debug, Serialize)]
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

#[derive(Serialize)]
struct WidgetStatus {
    ok: bool,
    configured: bool,
    error: Option<String>,
    config_path: String,
    interval_minutes: u64,
    threshold_yuan: f64,
    api_alert_enabled: bool,
    retention_days: u64,
    proxy_enabled: bool,
    language: String,
    ui_language: String,
    theme: String,
    icon_colors: BTreeMap<String, String>,
    icon_stroke: bool,
    last_check: String,
    total_currency: Option<String>,
    total_balance: Option<f64>,
    low_balance: bool,
    service_status: String,
    service_degraded: bool,
    consumption_rate: Option<ConsumptionRate>,
    history: Vec<HistoryRecord>,
    balances: BTreeMap<String, Balance>,
}

#[derive(Serialize)]
struct ConfigJson {
    #[serde(flatten)]
    config: AppConfig,
    has_key: bool,
}

#[derive(Deserialize)]
struct ApiResponse {
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

fn main() {
    process::exit(match run() {
        Ok(()) => 0,
        Err((code, message)) => {
            if !message.is_empty() {
                eprintln!("{message}");
            }
            code
        }
    });
}

fn run() -> Result<(), (i32, String)> {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str).unwrap_or("check") {
        "check" => check_once(),
        "daemon" => run_daemon(),
        "init-config" => init_config(),
        "config-path" => config_file().map_err(fail).and_then(print_path),
        "log-path" => log_file().map_err(fail).and_then(print_path),
        "clean-logs" => clean_logs(),
        "history" => print_history(&args[2..]),
        "widget-status" => print_widget_status(),
        "config-json" => print_config_json(),
        "set-key" => set_key(&args[2..]),
        "set" => set_config_field(&args[2..]),
        "set-config" => set_config(&args[2..]),
        "opencode-go" => opencode_go(&args[2..]),
        "command-code" => command_code(&args[2..]),
        "-V" | "--version" => {
            println!("dsmon {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        }
        "-h" | "--help" => {
            print_help();
            Ok(())
        }
        other => Err((1, format!("Unknown command: {other}\nRun: dsmon --help"))),
    }
}

fn check_once() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    prune_logs_on_startup(&config).map_err(fail)?;
    prune_balance_history(config.retention_days).map_err(fail)?;
    let checked_at = Local::now();
    let key = config.api_key.trim();
    if demo::is_enabled(key) {
        let conn = open_history_db().map_err(fail)?;
        demo::prepare(&conn).map_err(fail)?;
        let balances = demo::balances(&conn).map_err(fail)?;
        print_status(Some(&balances), None, checked_at, "none", &config);
        log_line("Demo balance check succeeded").map_err(fail)?;
        return Ok(());
    }
    let service_status = fetch_service_status(effective_http_proxy(&config));
    if key.is_empty() {
        ensure_config_file().map_err(fail)?;
        print_status(
            None,
            Some("DeepSeek API key is not configured.\nRun dsmon set-key <api_key> to store it securely."),
            checked_at,
            &service_status,
            &config,
        );
        return Err((2, String::new()));
    }
    let api_key = key.chars().filter(|c| c.is_ascii()).collect::<String>();
    match fetch_balance(&api_key, effective_http_proxy(&config)) {
        Ok(balances) => {
            save_balance_history(&balances, &service_status).map_err(fail)?;
            print_status(Some(&balances), None, checked_at, &service_status, &config);
            log_line("Balance check succeeded").map_err(fail)?;
            Ok(())
        }
        Err(error) => {
            print_status(None, Some(&error), checked_at, &service_status, &config);
            log_line(&format!("Balance check failed: {error}")).ok();
            Err((1, String::new()))
        }
    }
}

fn run_daemon() -> Result<(), (i32, String)> {
    let startup_config = load_config().map_err(fail)?;
    prune_logs_on_startup(&startup_config).map_err(fail)?;
    prune_balance_history(startup_config.retention_days).map_err(fail)?;
    let mut last_service_status = String::new();
    log_line("dsmon daemon started").map_err(fail)?;
    loop {
        let config = match load_config() {
            Ok(config) => config,
            Err(error) => {
                log_line(&format!("Failed to reload config: {error}")).ok();
                thread::sleep(Duration::from_secs(60));
                continue;
            }
        };
        let interval = Duration::from_secs(config.interval_minutes.clamp(1, 1440) * 60);
        let api_key = match require_api_key(&config) {
            Ok(api_key) => api_key,
            Err((_, message)) => {
                log_line(&message).ok();
                thread::sleep(interval);
                continue;
            }
        };
        if let Err(error) = prune_balance_history(config.retention_days) {
            log_line(&format!("Failed to prune balance history: {error}")).ok();
        }
        let demo_mode = demo::is_enabled(&api_key);
        let service_status = if demo_mode {
            "none".to_string()
        } else {
            fetch_service_status(effective_http_proxy(&config))
        };
        if !last_service_status.is_empty() && service_status != last_service_status {
            log_line(&format!(
                "DeepSeek API status changed: {}",
                service_status_text(&service_status)
            ))
            .ok();
        }
        last_service_status = service_status.clone();
        let balance_result = if demo_mode {
            let conn = open_history_db().map_err(fail)?;
            demo::prepare(&conn).map_err(fail)?;
            demo::balances(&conn)
        } else {
            fetch_balance(&api_key, effective_http_proxy(&config))
        };
        match balance_result {
            Ok(balances) => {
                if !demo_mode {
                    if let Err(error) = save_balance_history(&balances, &service_status) {
                        log_line(&format!("Failed to save balance history: {error}")).ok();
                    }
                }
                if demo_mode {
                    log_line(&format!(
                        "Demo balance check succeeded: {}",
                        summary(&balances)
                    ))
                    .ok();
                    thread::sleep(interval);
                    continue;
                }
                log_line(&format!("Balance check succeeded: {}", summary(&balances))).ok();
                if is_low_balance(&balances, config.threshold_yuan) {
                    log_line("Balance is below configured threshold").ok();
                }
            }
            Err(error) => {
                log_line(&format!("Balance check failed: {error}")).ok();
            }
        }
        thread::sleep(interval);
    }
}

fn init_config() -> Result<(), (i32, String)> {
    let path = config_file().map_err(fail)?;
    if !path.exists() {
        save_config(&AppConfig::default()).map_err(fail)?;
    }
    println!("Config file: {}", path.display());
    Ok(())
}

fn clean_logs() -> Result<(), (i32, String)> {
    let path = log_file().map_err(fail)?;
    match fs::remove_file(&path) {
        Ok(()) => println!("Removed log file: {}", path.display()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            println!("No log file found: {}", path.display())
        }
        Err(error) => return Err(fail(error)),
    }
    Ok(())
}

fn print_help() {
    println!(
        "Usage: dsmon [check|daemon|init-config|config-path|log-path|clean-logs|history|widget-status|config-json|set-key|set|set-config|opencode-go|command-code]\nHistory: dsmon history [days] | dsmon history export [days] [currency|all] [path|-]\nSet: dsmon set <field> <value>\nOpenCode Go: dsmon opencode-go | dsmon opencode-go set-key <api_key> | dsmon opencode-go json\nCommand Code: dsmon command-code | dsmon command-code set-key <api_key> | dsmon command-code json"
    );
}

fn print_path(path: PathBuf) -> Result<(), (i32, String)> {
    println!("{}", path.display());
    Ok(())
}

fn require_api_key(config: &AppConfig) -> Result<String, (i32, String)> {
    let key = config.api_key.trim();
    if key.is_empty() {
        let path = config_file().map_err(fail)?;
        ensure_config_file().map_err(fail)?;
        return Err((
            2,
            format!(
                "DeepSeek API key is not configured.\nRun dsmon set-key <api_key> to store it securely.\nConfig file: {}",
                path.display()
            ),
        ));
    }
    Ok(key.chars().filter(|c| c.is_ascii()).collect())
}

fn print_widget_status() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    prune_balance_history(config.retention_days).map_err(fail)?;
    let config_path = config_file()
        .map(|path| path.display().to_string())
        .map_err(fail)?;
    let checked_at = Local::now();
    let key = config.api_key.trim();
    let demo_mode = demo::is_enabled(key);
    let demo_conn = if demo_mode {
        let conn = open_history_db().map_err(fail)?;
        demo::prepare(&conn).map_err(fail)?;
        Some(conn)
    } else {
        None
    };
    let service_status = if demo_mode {
        "none".to_string()
    } else {
        fetch_service_status(effective_http_proxy(&config))
    };
    let service_degraded = is_service_degraded(&service_status);
    let latest_consumption_rate = if let Some(conn) = demo_conn.as_ref() {
        Some(demo::consumption_rate(conn).map_err(fail)?)
    } else {
        consumption_rate_with_fallback(config.retention_days, config.interval_minutes)
            .unwrap_or(None)
    };
    let history = if let Some(conn) = demo_conn.as_ref() {
        demo::history(conn, 24).map_err(fail)?
    } else {
        recent_balance_history(config.retention_days, 5).unwrap_or_default()
    };
    if key.is_empty() {
        ensure_config_file().map_err(fail)?;
        return write_widget_status(WidgetStatus {
            ok: false,
            configured: false,
            error: Some("DeepSeek API key is not configured.".to_string()),
            config_path,
            interval_minutes: config.interval_minutes,
            threshold_yuan: config.threshold_yuan,
            api_alert_enabled: config.api_alert_enabled,
            retention_days: config.retention_days,
            proxy_enabled: config.proxy_enabled,
            language: config.language.clone(),
            ui_language: config.ui_language.clone(),
            theme: config.theme.clone(),
            icon_colors: config.icon_colors.clone(),
            icon_stroke: config.icon_stroke,
            last_check: format_time(checked_at),
            total_currency: None,
            total_balance: None,
            low_balance: false,
            service_status,
            service_degraded,
            consumption_rate: latest_consumption_rate.clone(),
            history,
            balances: BTreeMap::new(),
        });
    }
    if demo_mode {
        let balances =
            demo::balances(demo_conn.as_ref().expect("demo connection exists")).map_err(fail)?;
        let (total_currency, total_balance) = preferred_balance(&balances)
            .map(|(currency, balance)| (Some(currency.clone()), Some(balance.total_balance)))
            .unwrap_or((None, None));
        return write_widget_status(WidgetStatus {
            ok: true,
            configured: true,
            error: None,
            config_path,
            interval_minutes: config.interval_minutes,
            threshold_yuan: config.threshold_yuan,
            api_alert_enabled: config.api_alert_enabled,
            retention_days: config.retention_days,
            proxy_enabled: config.proxy_enabled,
            language: config.language.clone(),
            ui_language: config.ui_language.clone(),
            theme: config.theme.clone(),
            icon_colors: config.icon_colors.clone(),
            icon_stroke: config.icon_stroke,
            last_check: format_time(checked_at),
            total_currency,
            total_balance,
            low_balance: false,
            service_status,
            service_degraded,
            consumption_rate: latest_consumption_rate.clone(),
            history,
            balances,
        });
    }
    let api_key = key.chars().filter(|c| c.is_ascii()).collect::<String>();
    match fetch_balance(&api_key, effective_http_proxy(&config)) {
        Ok(balances) => {
            save_balance_history(&balances, &service_status).map_err(fail)?;
            let (total_currency, total_balance) = preferred_balance(&balances)
                .map(|(currency, balance)| (Some(currency.clone()), Some(balance.total_balance)))
                .unwrap_or((None, None));
            let history = recent_balance_history(config.retention_days, 5).unwrap_or_default();
            let rate =
                consumption_rate_with_fallback(config.retention_days, config.interval_minutes)
                    .unwrap_or(None);
            write_widget_status(WidgetStatus {
                ok: true,
                configured: true,
                error: None,
                config_path,
                interval_minutes: config.interval_minutes,
                threshold_yuan: config.threshold_yuan,
                api_alert_enabled: config.api_alert_enabled,
                retention_days: config.retention_days,
                proxy_enabled: config.proxy_enabled,
                language: config.language.clone(),
                ui_language: config.ui_language.clone(),
                theme: config.theme.clone(),
                icon_colors: config.icon_colors.clone(),
                icon_stroke: config.icon_stroke,
                last_check: format_time(checked_at),
                total_currency,
                total_balance,
                low_balance: is_low_balance(&balances, config.threshold_yuan),
                service_status: service_status.clone(),
                service_degraded,
                consumption_rate: rate.clone(),
                history,
                balances,
            })
        }
        Err(error) => {
            let cached_balances = balances_from_history(&history);
            if service_degraded && !cached_balances.is_empty() {
                let (total_currency, total_balance) = preferred_balance(&cached_balances)
                    .map(|(currency, balance)| {
                        (Some(currency.clone()), Some(balance.total_balance))
                    })
                    .unwrap_or((None, None));
                write_widget_status(WidgetStatus {
                    ok: true,
                    configured: true,
                    error: None,
                    config_path,
                    interval_minutes: config.interval_minutes,
                    threshold_yuan: config.threshold_yuan,
                    api_alert_enabled: config.api_alert_enabled,
                    retention_days: config.retention_days,
                    proxy_enabled: config.proxy_enabled,
                    language: config.language.clone(),
                    ui_language: config.ui_language.clone(),
                    theme: config.theme.clone(),
                    icon_colors: config.icon_colors.clone(),
                    icon_stroke: config.icon_stroke,
                    last_check: history
                        .last()
                        .map(|record| record.timestamp.clone())
                        .unwrap_or_else(|| format_time(checked_at)),
                    total_currency,
                    total_balance,
                    low_balance: is_low_balance(&cached_balances, config.threshold_yuan),
                    service_status,
                    service_degraded,
                    consumption_rate: latest_consumption_rate.clone(),
                    history,
                    balances: cached_balances,
                })
            } else {
                write_widget_status(WidgetStatus {
                    ok: false,
                    configured: true,
                    error: Some(error),
                    config_path,
                    interval_minutes: config.interval_minutes,
                    threshold_yuan: config.threshold_yuan,
                    api_alert_enabled: config.api_alert_enabled,
                    retention_days: config.retention_days,
                    proxy_enabled: config.proxy_enabled,
                    language: config.language.clone(),
                    ui_language: config.ui_language.clone(),
                    theme: config.theme.clone(),
                    icon_colors: config.icon_colors.clone(),
                    icon_stroke: config.icon_stroke,
                    last_check: format_time(checked_at),
                    total_currency: None,
                    total_balance: None,
                    low_balance: false,
                    service_status,
                    service_degraded,
                    consumption_rate: latest_consumption_rate.clone(),
                    history,
                    balances: BTreeMap::new(),
                })
            }
        }
    }
}

fn write_widget_status(status: WidgetStatus) -> Result<(), (i32, String)> {
    let text = serde_json::to_string(&status).map_err(fail)?;
    println!("{text}");
    Ok(())
}

fn print_config_json() -> Result<(), (i32, String)> {
    let mut config = load_config().map_err(fail)?;
    let has_key = !config.api_key.trim().is_empty();
    config.api_key = if has_key {
        API_KEY_MASK.to_string()
    } else {
        String::new()
    };
    println!(
        "{}",
        serde_json::to_string(&ConfigJson { config, has_key }).map_err(fail)?
    );
    Ok(())
}

fn print_history(args: &[String]) -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    match args.first().map(String::as_str) {
        Some("export") => export_history(&args[1..], &config),
        Some("json") => {
            print_history_json(&args[1..], config.retention_days, config.interval_minutes)
        }
        _ => print_history_summary(args, config.retention_days, config.interval_minutes),
    }
}

fn print_history_summary(
    args: &[String],
    default_days: u64,
    interval_minutes: u64,
) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), default_days)?;
    let report = history_report(days, None, usize::MAX, interval_minutes).map_err(fail)?;
    if report.records.is_empty() {
        println!("No balance history.");
        return Ok(());
    }
    println!("Balance history summary (last {days} days)");
    println!("Records: {}", report.total_records);
    println!("Currencies: {}", report.currencies.join(", "));
    for item in report.summary {
        println!();
        println!("{}:", item.currency);
        println!("  First check: {}", item.first_time);
        println!("  Last check: {}", item.last_time);
        println!(
            "  Latest: total={} topped={} granted={}",
            format_amount(item.latest_total),
            format_amount(item.latest_topped),
            format_amount(item.latest_granted)
        );
        println!(
            "  Total min/max/avg: {}/{}/{}",
            format_amount(item.min_total),
            format_amount(item.max_total),
            format_amount(item.avg_total)
        );
        println!("  Change: {}", format_signed_amount(item.change_total));
    }
    println!();
    println!("Export raw CSV: dsmon history export {days} all");
    Ok(())
}

fn print_history_json(
    args: &[String],
    default_days: u64,
    interval_minutes: u64,
) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), default_days)?;
    let currency = history_currency(args.get(1));
    let report = history_report(days, currency.as_deref(), 500, interval_minutes).map_err(fail)?;
    println!("{}", serde_json::to_string(&report).map_err(fail)?);
    Ok(())
}

fn export_history(args: &[String], config: &AppConfig) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), config.retention_days)?;
    let currency = history_currency(args.get(1));
    let records = history_records(days, currency.as_deref(), usize::MAX).map_err(fail)?;
    let csv = history_csv(&records);
    match args.get(2).map(String::as_str) {
        Some("-") => print!("{csv}"),
        path => {
            let path = path
                .map(PathBuf::from)
                .map(Ok)
                .unwrap_or_else(|| history_export_file(&config.export_path))
                .map_err(fail)?;
            if let Some(parent) = path.parent() {
                ensure_dir(parent).map_err(fail)?;
            }
            fs::write(&path, csv).map_err(fail)?;
            println!("Exported: {}", path.display());
        }
    }
    Ok(())
}

fn parse_history_days(value: Option<&String>, default_days: u64) -> Result<u64, (i32, String)> {
    value
        .map(|value| value.parse::<u64>().map_err(fail))
        .transpose()
        .map(|days| days.unwrap_or(default_days).clamp(1, 3650))
}

fn history_currency(value: Option<&String>) -> Option<String> {
    value
        .map(|value| value.trim())
        .filter(|value| !value.is_empty() && !value.eq_ignore_ascii_case("all"))
        .map(str::to_string)
}

fn history_report(
    days: u64,
    currency: Option<&str>,
    limit: usize,
    interval_minutes: u64,
) -> Result<HistoryReport, String> {
    let records = history_records(days, currency, limit)?;
    Ok(HistoryReport {
        days,
        currency: currency.unwrap_or("all").to_string(),
        currencies: history_currencies(days)?,
        total_records: records.len(),
        summary: summarize_history(&records),
        consumption_rate: consumption_rate_with_fallback(days, interval_minutes)?,
        records,
    })
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

fn consumption_rate(hours: i64, interval_minutes: u64) -> Result<Option<ConsumptionRate>, String> {
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
    let cutoff = format_time(Local::now() - ChronoDuration::hours(hours.max(1)));
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

fn set_key(args: &[String]) -> Result<(), (i32, String)> {
    let api_key = if let Some(value) = args.first() {
        value.trim().to_string()
    } else {
        let mut value = String::new();
        std::io::stdin().read_line(&mut value).map_err(fail)?;
        value.trim().to_string()
    };
    if api_key.is_empty() {
        return Err((2, "DeepSeek API key is required.".to_string()));
    }
    let mut config = load_config().unwrap_or_default();
    store_secure_api_key(&api_key).map_err(fail)?;
    config.api_key.clear();
    save_config(&config).map_err(fail)?;
    println!("API key saved.");
    Ok(())
}

fn set_config_field(args: &[String]) -> Result<(), (i32, String)> {
    if args.len() < 2 {
        return Err(fail(
            "Usage: dsmon set <field> <value>\nFields: interval, threshold, ui-language, auto-start, alert-mode, api-alert-enabled, retention-days, export-path, http-proxy, proxy-enabled, theme, icon-stroke, icon-colors, color-ok, color-low, color-degraded, color-nodata",
        ));
    }
    let mut config = load_config().unwrap_or_default();
    let sync_auto_start = apply_config_field(&mut config, &args[0], &args[1..]).map_err(fail)?;
    normalize_config(&mut config);
    save_config(&config).map_err(fail)?;
    if sync_auto_start {
        set_auto_start(config.auto_start).map_err(fail)?;
    }
    println!("Config saved.");
    Ok(())
}

fn apply_config_field(
    config: &mut AppConfig,
    field: &str,
    values: &[String],
) -> Result<bool, String> {
    let value = values
        .first()
        .map(|value| value.trim())
        .ok_or_else(|| "Missing field value.".to_string())?;
    match field {
        "interval" | "interval-minutes" | "interval_minutes" => {
            let minutes = value.parse::<u64>().map_err(|e| e.to_string())?;
            if !(1..=1440).contains(&minutes) {
                return Err("Interval minutes must be between 1 and 1440.".to_string());
            }
            config.interval_minutes = minutes;
        }
        "threshold" | "threshold-yuan" | "threshold_yuan" => {
            let threshold = value.parse::<f64>().map_err(|e| e.to_string())?;
            if !(0.0..=10000.0).contains(&threshold) {
                return Err("Balance threshold must be between 0 and 10000.".to_string());
            }
            config.threshold_yuan = threshold;
        }
        "ui-language" | "ui_language" => {
            if !matches!(value, "zh" | "en") {
                return Err("UI language must be zh or en.".to_string());
            }
            config.ui_language = value.to_string();
        }
        "language" => {
            return Err(
                "language is fixed to en for CLI; use ui-language for UI text.".to_string(),
            );
        }
        "auto-start" | "auto_start" => {
            config.auto_start = parse_bool_arg(value)?;
            return Ok(true);
        }
        "alert-mode" | "alert_mode" => {
            config.alert_mode = parse_alert_mode_arg(value)?;
        }
        "api-alert-enabled" | "api_alert_enabled" => {
            config.api_alert_enabled = parse_bool_arg(value)?;
        }
        "retention-days" | "retention_days" | "retention" => {
            let days = value.parse::<u64>().map_err(|e| e.to_string())?;
            if !(1..=3650).contains(&days) {
                return Err("Retention days must be between 1 and 3650.".to_string());
            }
            config.retention_days = days;
        }
        "export-path" | "export_path" => {
            config.export_path = value.to_string();
        }
        "http-proxy" | "http_proxy" | "proxy" => {
            config.http_proxy = value.to_string();
        }
        "proxy-enabled" | "proxy_enabled" => {
            config.proxy_enabled = parse_bool_arg(value)?;
        }
        "theme" => {
            config.theme = parse_theme_arg(value)?;
            if config.theme != "custom" {
                config.icon_colors.clear();
            }
        }
        "icon-stroke" | "icon_stroke" => {
            config.icon_stroke = parse_bool_arg(value)?;
        }
        "icon-colors" | "icon_colors" => {
            if values.len() != 4 {
                return Err("icon-colors requires: ok low degraded nodata".to_string());
            }
            config.icon_colors = parse_icon_colors(values)?;
            config.theme = "custom".to_string();
        }
        "color-ok" | "color-low" | "color-degraded" | "color-nodata" => {
            let key = field.trim_start_matches("color-");
            if !is_hex_color(value.trim_start_matches('#')) {
                return Err(format!("{key} color must be a 6-digit hex value."));
            }
            config
                .icon_colors
                .insert(key.to_string(), value.trim_start_matches('#').to_string());
            config.theme = "custom".to_string();
        }
        "api-key" | "api_key" => {
            return Err("Use dsmon set-key to update the encrypted API key.".to_string());
        }
        _ => return Err(format!("Unknown config field: {field}")),
    }
    Ok(false)
}

fn set_config(args: &[String]) -> Result<(), (i32, String)> {
    if !(7..=16).contains(&args.len()) {
        return Err(fail(
            "Usage: dsmon set-config <api_key> <interval_minutes> <threshold_yuan> <ui_language> <auto_start> <alert_mode> [api_alert_enabled] <retention_days> [export_path] [http_proxy] [theme] [icon_stroke] [ok_hex low_hex degraded_hex nodata_hex]",
        ));
    }
    let api_key = args[0].trim();
    let mut config = load_config().unwrap_or_default();
    let has_existing_key = !config.api_key.trim().is_empty();
    if api_key.is_empty() || api_key == API_KEY_MASK {
        if !has_existing_key {
            return Err((2, "DeepSeek API key is required.".to_string()));
        }
    } else {
        store_secure_api_key(api_key).map_err(fail)?;
    }
    let threshold_yuan = args[2].parse::<f64>().map_err(fail)?;
    if !(0.0..=10000.0).contains(&threshold_yuan) {
        return Err(fail("Balance threshold must be between 0 and 10000."));
    }
    config.api_key.clear();
    config.interval_minutes = args[1].parse::<u64>().map_err(fail)?.clamp(1, 1440);
    config.threshold_yuan = threshold_yuan;
    config.language = default_lang();
    config.ui_language = if args[3] == "zh" { "zh" } else { "en" }.to_string();
    config.auto_start = parse_bool_arg(&args[4]).map_err(fail)?;
    config.alert_mode = parse_alert_mode_arg(&args[5]).map_err(fail)?;
    if args.len() >= 8 {
        config.api_alert_enabled = parse_bool_arg(&args[6]).map_err(fail)?;
    }
    let retention_arg = if args.len() >= 8 { &args[7] } else { &args[6] };
    config.retention_days = retention_arg.parse::<u64>().map_err(fail)?.clamp(1, 3650);
    let tail: &[String] = if args.len() >= 8 { &args[8..] } else { &[] };
    match tail.len() {
        0 => {}
        1 if tail[0].trim().starts_with("http://") || tail[0].trim().starts_with("https://") => {
            config.http_proxy = tail[0].trim().to_string();
        }
        1 => {
            config.export_path = tail[0].trim().to_string();
        }
        2 if parse_theme_arg(&tail[1]).is_ok() => {
            config.http_proxy = tail[0].trim().to_string();
            config.theme = parse_theme_arg(&tail[1]).map_err(fail)?;
        }
        2 | 4 | 8 => {
            config.export_path = tail[0].trim().to_string();
            if tail.len() >= 2 {
                config.http_proxy = tail[1].trim().to_string();
            }
            if tail.len() >= 4 {
                config.theme = parse_theme_arg(&tail[2]).map_err(fail)?;
                config.icon_stroke = parse_bool_arg(&tail[3]).map_err(fail)?;
            }
            if tail.len() == 8 {
                config.icon_colors = parse_icon_colors(&tail[4..8]).map_err(fail)?;
            }
        }
        3 | 7 => {
            config.http_proxy = tail[0].trim().to_string();
            config.theme = parse_theme_arg(&tail[1]).map_err(fail)?;
            config.icon_stroke = parse_bool_arg(&tail[2]).map_err(fail)?;
            if tail.len() == 7 {
                config.icon_colors = parse_icon_colors(&tail[3..7]).map_err(fail)?;
            }
        }
        _ => return Err(fail("Invalid set-config argument count.")),
    }
    if config.theme != "custom" {
        config.icon_colors.clear();
    }
    normalize_config(&mut config);
    save_config(&config).map_err(fail)?;
    set_auto_start(config.auto_start).map_err(fail)?;
    println!("Config saved.");
    Ok(())
}

fn opencode_go(args: &[String]) -> Result<(), (i32, String)> {
    match args.first().map(String::as_str) {
        Some("set") | Some("set-key") => opencode_go_set_key(&args[1..]),
        Some("json") => opencode_go_json(),
        Some(other) => Err(fail(format!(
            "Unknown opencode-go subcommand: {other}\nRun: dsmon opencode-go set-key <api_key>"
        ))),
        None => opencode_go_check(),
    }
}

fn opencode_go_set_key(args: &[String]) -> Result<(), (i32, String)> {
    let api_key = if let Some(value) = args.first() {
        value.trim().to_string()
    } else {
        let mut value = String::new();
        std::io::stdin().read_line(&mut value).map_err(fail)?;
        value.trim().to_string()
    };
    if api_key.is_empty() {
        return Err((2, "OpenCode Go API key is required.".to_string()));
    }
    store_secure_value(OPENCODE_GO_API_KEY, &api_key).map_err(fail)?;
    println!("OpenCode Go API key saved.");
    Ok(())
}

fn opencode_go_check() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    let api_key = read_secure_value(OPENCODE_GO_API_KEY)
        .map_err(fail)?
        .unwrap_or_default();
    if api_key.is_empty() {
        return Err((
            2,
            "OpenCode Go API key is not configured.\nRun: dsmon opencode-go set-key <api_key>"
                .to_string(),
        ));
    }
    match fetch_opencode_go_quota(&api_key, effective_http_proxy(&config)) {
        Ok(quota) => {
            print_opencode_go_quota(&quota);
            Ok(())
        }
        Err(error) => Err((1, error)),
    }
}

fn opencode_go_json() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    let api_key = read_secure_value(OPENCODE_GO_API_KEY)
        .map_err(fail)?
        .unwrap_or_default();
    let payload = if api_key.is_empty() {
        serde_json::json!({
            "configured": false,
            "error": "OpenCode Go API key is not configured.\nRun: dsmon opencode-go set-key <api_key>"
        })
    } else {
        match fetch_opencode_go_quota(&api_key, effective_http_proxy(&config)) {
            Ok(quota) => serde_json::json!({
                "configured": true,
                "error": null,
                "rolling": quota.rolling,
                "weekly": quota.weekly,
                "monthly": quota.monthly
            }),
            Err(error) => serde_json::json!({
                "configured": true,
                "error": error,
                "rolling": null,
                "weekly": null,
                "monthly": null
            }),
        }
    };
    println!("{payload}");
    Ok(())
}

fn print_opencode_go_quota(quota: &OpenCodeGoQuota) {
    println!("OpenCode Go:");
    print_opencode_go_window("5h", quota.rolling.as_ref());
    print_opencode_go_window("Weekly", quota.weekly.as_ref());
    print_opencode_go_window("Monthly", quota.monthly.as_ref());
}

fn print_opencode_go_window(label: &str, usage: Option<&OpenCodeGoUsage>) {
    match usage {
        Some(usage) => println!(
            "  {label:<8} {:.0}% used | {:.0}% remaining | resets in {}",
            usage.usage_percent,
            usage.percent_remaining,
            format_reset_seconds(usage.reset_in_sec)
        ),
        None => println!("  {label:<8} (unavailable)"),
    }
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

fn command_code(args: &[String]) -> Result<(), (i32, String)> {
    match args.first().map(String::as_str) {
        Some("set") | Some("set-key") => command_code_set_key(&args[1..]),
        Some("json") => command_code_json(),
        Some(other) => Err(fail(format!(
            "Unknown command-code subcommand: {other}\nRun: dsmon command-code set-key <api_key>"
        ))),
        None => command_code_check(),
    }
}

fn command_code_set_key(args: &[String]) -> Result<(), (i32, String)> {
    let api_key = if let Some(value) = args.first() {
        value.trim().to_string()
    } else {
        let mut value = String::new();
        std::io::stdin().read_line(&mut value).map_err(fail)?;
        value.trim().to_string()
    };
    if api_key.is_empty() {
        return Err((2, "Command Code API key is required.".to_string()));
    }
    store_secure_value(COMMAND_CODE_API_KEY, &api_key).map_err(fail)?;
    println!("Command Code API key saved.");
    Ok(())
}

fn command_code_check() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    let api_key = read_secure_value(COMMAND_CODE_API_KEY)
        .map_err(fail)?
        .unwrap_or_default();
    if api_key.is_empty() {
        return Err((
            2,
            "Command Code API key is not configured.\nRun: dsmon command-code set-key <api_key>"
                .to_string(),
        ));
    }
    match fetch_command_code_quota(&api_key, effective_http_proxy(&config)) {
        Ok(quota) => {
            print_command_code_quota(&quota);
            Ok(())
        }
        Err(error) => Err((1, error)),
    }
}

fn command_code_json() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    let api_key = read_secure_value(COMMAND_CODE_API_KEY)
        .map_err(fail)?
        .unwrap_or_default();
    let payload = if api_key.is_empty() {
        serde_json::json!({
            "configured": false,
            "error": "Command Code API key is not configured.\nRun: dsmon command-code set-key <api_key>"
        })
    } else {
        match fetch_command_code_quota(&api_key, effective_http_proxy(&config)) {
            Ok(quota) => serde_json::json!({
                "configured": true,
                "error": null,
                "five_hour": quota.five_hour,
                "weekly": quota.weekly,
                "monthly": quota.monthly
            }),
            Err(error) => serde_json::json!({
                "configured": true,
                "error": error,
                "five_hour": null,
                "weekly": null,
                "monthly": null
            }),
        }
    };
    println!("{payload}");
    Ok(())
}

fn print_command_code_quota(quota: &CommandCodeQuota) {
    println!("Command Code:");
    print_command_code_window("5h", quota.five_hour.as_ref());
    print_command_code_window("Weekly", quota.weekly.as_ref());
    print_command_code_window("Monthly", quota.monthly.as_ref());
}

fn print_command_code_window(label: &str, window: Option<&CommandCodeWindow>) {
    match window {
        Some(window) => println!(
            "  {label:<8} {:.1}/{:.1} used | resets in {}",
            window.used,
            window.cap,
            format_reset_seconds(window.reset_in_sec)
        ),
        None => println!("  {label:<8} (unavailable)"),
    }
}

fn fetch_command_code_quota(api_key: &str, http_proxy: &str) -> Result<CommandCodeQuota, String> {
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
    let monthly_cap = payload
        .window_limits
        .five_hour
        .as_ref()
        .zip(payload.window_limits.weekly.as_ref())
        .and_then(|(five_hour, weekly)| {
            command_code_monthly_cap(five_hour.cap.max(0.0), weekly.cap.max(0.0))
        });
    let monthly = command_code_monthly_window(monthly_cap, payload.credits.monthly_credits);
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

/// Plan credit pools keyed by the plan's rolling window caps, per
/// https://commandcode.ai/docs/resources/usage-limits (verified 2026-09).
/// (5h cap, weekly cap) -> monthly credits; every plan is unique here.
fn command_code_monthly_cap(five_hour_cap: f64, weekly_cap: f64) -> Option<f64> {
    match (five_hour_cap.round() as i64, weekly_cap.round() as i64) {
        (3, 6) => Some(10.0),     // Go
        (14, 35) => Some(70.0),   // GOAT
        (16, 40) => Some(80.0),   // Pro
        (45, 90) => Some(150.0),  // Max 10x
        (90, 180) => Some(300.0), // Max 20x
        (12, 24) => Some(40.0),   // Team Pro
        // 未收录档位（含无窗口的纯充值账号）：不推算月度
        _ => None,
    }
}

fn command_code_monthly_window(
    monthly_cap: Option<f64>,
    monthly_credits: Option<f64>,
) -> Option<CommandCodeWindow> {
    monthly_cap
        .zip(monthly_credits)
        .map(|(cap, remaining)| CommandCodeWindow {
            used: (cap - remaining).clamp(0.0, cap),
            cap,
            reset_in_sec: 0,
        })
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

fn fetch_balance(api_key: &str, http_proxy: &str) -> Result<BTreeMap<String, Balance>, String> {
    let client = http_client(Duration::from_secs(15), http_proxy)?;
    let response = client
        .get("https://api.deepseek.com/user/balance")
        .header("Accept", "application/json")
        .bearer_auth(api_key)
        .send()
        .map_err(|e| e.to_string())?;
    if response.status() == StatusCode::UNAUTHORIZED {
        return Err("Invalid API key (401 Unauthorized)".to_string());
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

fn fetch_service_status(http_proxy: &str) -> String {
    let Ok(client) = http_client(Duration::from_secs(10), http_proxy) else {
        return "unknown".to_string();
    };
    fetch_flashduty_api_status(&client)
        .unwrap_or("unknown")
        .to_string()
}

fn http_client(timeout: Duration, http_proxy: &str) -> Result<reqwest::blocking::Client, String> {
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

fn fetch_flashduty_api_status(client: &reqwest::blocking::Client) -> Option<&'static str> {
    let html = client
        .get("https://status.flashcat.cloud/deepseek")
        .header("Accept", "text/html,*/*")
        .header("User-Agent", "Mozilla/5.0")
        .send()
        .ok()?
        .error_for_status()
        .ok()?
        .text()
        .ok()?;
    Some(parse_flashduty_api_status(&html))
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

fn print_status(
    balances: Option<&BTreeMap<String, Balance>>,
    error: Option<&str>,
    checked_at: DateTime<Local>,
    service_status: &str,
    config: &AppConfig,
) {
    println!("DeepSeek Balance:");
    let has_balance =
        if let Some((currency, balance)) = balances.and_then(|items| preferred_balance(items)) {
            println!(
                "💰 {} {} (Topped {}, Granted {})",
                format_amount(balance.total_balance),
                currency,
                format_amount(balance.topped_up_balance),
                format_amount(balance.granted_balance)
            );
            if let Ok(Some(rate)) =
                consumption_rate_with_fallback(config.retention_days, config.interval_minutes)
            {
                println!("📊 {}", consumption_rate_line(&rate));
            }
            true
        } else {
            false
        };
    if !has_balance {
        if let Some(error) = error {
            println!("🕐 Query error: {error}");
        } else {
            println!("🕐 Not checked");
        }
    }
    println!(
        "📡 DeepSeek API Status: {}",
        service_status_notification_label(service_status)
    );
    if has_balance && error.is_none() {
        println!(
            "🕐 Last Check: {}",
            relative_time_en(checked_at, Local::now())
        );
    }
}

fn summary(balances: &BTreeMap<String, Balance>) -> String {
    balances
        .iter()
        .map(|(currency, balance)| {
            format!("{currency} total={}", format_amount(balance.total_balance))
        })
        .collect::<Vec<_>>()
        .join(", ")
}

fn preferred_balance(balances: &BTreeMap<String, Balance>) -> Option<(&String, &Balance)> {
    balances
        .get_key_value("CNY")
        .or_else(|| balances.iter().next())
}

fn balances_from_history(records: &[HistoryRecord]) -> BTreeMap<String, Balance> {
    let mut balances = BTreeMap::new();
    for record in records {
        balances.insert(
            record.currency.clone(),
            Balance {
                total_balance: record.total,
                topped_up_balance: record.topped,
                granted_balance: record.granted,
            },
        );
    }
    balances
}

fn is_service_degraded(status: &str) -> bool {
    matches!(status, "maintenance" | "minor" | "major" | "critical")
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

fn service_status_text(status: &str) -> &'static str {
    match status {
        "none" => "All Systems Operational",
        "minor" => "Minor Outage",
        "major" => "Major Outage",
        "critical" => "Critical Outage",
        "maintenance" => "Under Maintenance",
        _ => "Status Unknown",
    }
}

fn service_status_notification_label(status: &str) -> String {
    let emoji = match status {
        "none" => "🟢",
        "minor" | "maintenance" => "🟡",
        "major" => "🟠",
        "critical" => "🔴",
        _ => "⚪",
    };
    format!("{} {}", emoji, service_status_text(status))
}

fn consumption_rate_line(rate: &ConsumptionRate) -> String {
    let days = (rate.busy_hours_left / 24.0).floor() as i64;
    let hours = (rate.busy_hours_left % 24.0).floor() as i64;
    format!(
        "Busy: {:.2}/hr | Est. {}d {}h remaining",
        rate.hourly_rate, days, hours
    )
}

fn relative_time_en(value: DateTime<Local>, now: DateTime<Local>) -> String {
    let seconds = (now - value).num_seconds().max(0);
    if seconds < 60 {
        "just now".to_string()
    } else if seconds < 3600 {
        format!("{} minutes ago", seconds / 60)
    } else if seconds < 86400 {
        format!("{} hours ago", seconds / 3600)
    } else {
        format!("{} days ago", seconds / 86400)
    }
}

fn is_low_balance(balances: &BTreeMap<String, Balance>, threshold: f64) -> bool {
    preferred_balance(balances)
        .map(|(_, balance)| balance.total_balance < threshold)
        .unwrap_or(false)
}

fn parse_bool_arg(value: &str) -> Result<bool, String> {
    match value {
        "true" | "1" | "yes" | "on" => Ok(true),
        "false" | "0" | "no" | "off" => Ok(false),
        _ => Err(format!("Invalid boolean value: {value}")),
    }
}

fn parse_alert_mode_arg(value: &str) -> Result<String, String> {
    match value {
        "never" | "always" | "once" => Ok(value.to_string()),
        _ => Ok((if parse_bool_arg(value)? {
            "once"
        } else {
            "never"
        })
        .to_string()),
    }
}

fn parse_theme_arg(value: &str) -> Result<String, String> {
    match value {
        "default" | "contrast" | "bright" | "dark_mode" | "mono" | "custom" => {
            Ok(value.to_string())
        }
        _ => Err(
            "theme must be one of: default, contrast, bright, dark_mode, mono, custom".to_string(),
        ),
    }
}

fn parse_icon_colors(values: &[String]) -> Result<BTreeMap<String, String>, String> {
    let keys = ["ok", "low", "degraded", "nodata"];
    let mut colors = BTreeMap::new();
    for (key, value) in keys.into_iter().zip(values.iter()) {
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

fn set_auto_start(enable: bool) -> Result<(), String> {
    let action = if enable { "enable" } else { "disable" };
    let output = std::process::Command::new("systemctl")
        .args(["--user", action, "--now", "dsmon.service"])
        .output()
        .map_err(|e| e.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

fn load_config() -> Result<AppConfig, String> {
    let path = config_file().map_err(|e| e.to_string())?;
    if !path.exists() {
        save_config(&AppConfig::default()).map_err(|e| e.to_string())?;
    }
    let text = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let mut config = serde_json::from_str::<AppConfig>(&text).map_err(|e| e.to_string())?;
    let legacy_api_key = config.api_key.trim().to_string();
    let had_legacy_api_key = !legacy_api_key.is_empty();
    let previous_language = config.language.clone();
    let previous_ui_language = config.ui_language.clone();
    let missing_ui_language = !text.contains("\"ui_language\"");
    normalize_config(&mut config);
    let migrated_api_key = if had_legacy_api_key {
        store_secure_api_key(&legacy_api_key)?;
        legacy_api_key
    } else {
        read_secure_api_key()?.unwrap_or_default()
    };
    config.api_key = migrated_api_key;
    if missing_ui_language
        || previous_language != config.language
        || previous_ui_language != config.ui_language
        || had_legacy_api_key
    {
        save_config(&config).map_err(|e| e.to_string())?;
    }
    Ok(config)
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
    ensure_dir(&config_dir()?)?;
    let mut safe = config.clone();
    safe.api_key.clear();
    let file = File::create(config_file()?)?;
    serde_json::to_writer_pretty(file, &safe)?;
    Ok(())
}

fn ensure_config_file() -> std::io::Result<()> {
    if !config_file()?.exists() {
        save_config(&AppConfig::default())?;
    }
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
        params!["api_key", encrypted, format_time(Local::now())],
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
        params![key, encrypted, format_time(Local::now())],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

fn encrypt_secret(plaintext: &str) -> Result<Vec<u8>, String> {
    let key_bytes = read_or_create_secret_key()?;
    let key = LessSafeKey::new(
        UnboundKey::new(&AES_256_GCM, &key_bytes).map_err(|_| "Invalid secure key".to_string())?,
    );
    let mut nonce_bytes = [0u8; NONCE_LEN];
    SystemRandom::new()
        .fill(&mut nonce_bytes)
        .map_err(|_| "Failed to generate secure nonce".to_string())?;
    let nonce = Nonce::assume_unique_for_key(nonce_bytes);
    let mut payload = plaintext.as_bytes().to_vec();
    key.seal_in_place_append_tag(nonce, Aad::from(SECURE_AAD), &mut payload)
        .map_err(|_| "Failed to encrypt API key".to_string())?;
    let mut encrypted = Vec::with_capacity(SECURE_PREFIX.len() + NONCE_LEN + payload.len());
    encrypted.extend_from_slice(SECURE_PREFIX);
    encrypted.extend_from_slice(&nonce_bytes);
    encrypted.extend_from_slice(&payload);
    Ok(encrypted)
}

fn decrypt_secret(encrypted: &[u8]) -> Result<String, String> {
    if encrypted.len() <= SECURE_PREFIX.len() + NONCE_LEN || !encrypted.starts_with(SECURE_PREFIX) {
        return Err("Invalid encrypted API key format".to_string());
    }
    let key_bytes = read_or_create_secret_key()?;
    let key = LessSafeKey::new(
        UnboundKey::new(&AES_256_GCM, &key_bytes).map_err(|_| "Invalid secure key".to_string())?,
    );
    let mut nonce_bytes = [0u8; NONCE_LEN];
    let nonce_start = SECURE_PREFIX.len();
    nonce_bytes.copy_from_slice(&encrypted[nonce_start..nonce_start + NONCE_LEN]);
    let nonce = Nonce::assume_unique_for_key(nonce_bytes);
    let mut payload = encrypted[nonce_start + NONCE_LEN..].to_vec();
    let plaintext = key
        .open_in_place(nonce, Aad::from(SECURE_AAD), &mut payload)
        .map_err(|_| "Failed to decrypt API key".to_string())?;
    String::from_utf8(plaintext.to_vec()).map_err(|e| e.to_string())
}

fn read_or_create_secret_key() -> Result<[u8; 32], String> {
    let path = secure_key_file().map_err(|e| e.to_string())?;
    match fs::read(&path) {
        Ok(bytes) if bytes.len() == 32 => {
            let mut key = [0u8; 32];
            key.copy_from_slice(&bytes);
            Ok(key)
        }
        Ok(_) => Err(format!("Invalid secure key file: {}", path.display())),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            ensure_dir(&state_dir().map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
            let mut key = [0u8; 32];
            SystemRandom::new()
                .fill(&mut key)
                .map_err(|_| "Failed to generate secure key".to_string())?;
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&path)
                .map_err(|e| e.to_string())?;
            file.write_all(&key).map_err(|e| e.to_string())?;
            Ok(key)
        }
        Err(error) => Err(error.to_string()),
    }
}

fn log_line(message: &str) -> std::io::Result<()> {
    ensure_dir(&state_dir()?)?;
    let path = log_file()?;
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(file, "[{}] {}", format_time(Local::now()), message)
}

fn save_balance_history(
    balances: &BTreeMap<String, Balance>,
    service_status: &str,
) -> Result<(), String> {
    let mut conn = open_history_db()?;
    let timestamp = format_time(Local::now());
    let dedup_cutoff = format_time(Local::now() - ChronoDuration::seconds(HISTORY_DEDUP_SECONDS));
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
    let conn = open_history_db()?;
    let cutoff = format_time(Local::now() - ChronoDuration::days(days as i64));
    let limit = i64::try_from(limit).unwrap_or(i64::MAX);
    let mut stmt = conn
        .prepare(
            "SELECT timestamp, currency, total, topped, granted, service_status FROM (
                SELECT timestamp, currency, total, topped, granted, service_status
                FROM balance_history
                WHERE timestamp >= ?1
                ORDER BY timestamp DESC
                LIMIT ?2
             ) ORDER BY timestamp ASC",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params![cutoff, limit], history_record_from_row)
        .map_err(|e| e.to_string())?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row.map_err(|e| e.to_string())?);
    }
    Ok(records)
}

fn history_records(
    days: u64,
    currency: Option<&str>,
    limit: usize,
) -> Result<Vec<HistoryRecord>, String> {
    let conn = open_history_db()?;
    let cutoff = format_time(Local::now() - ChronoDuration::days(days as i64));
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

fn history_currencies(days: u64) -> Result<Vec<String>, String> {
    let conn = open_history_db()?;
    let cutoff = format_time(Local::now() - ChronoDuration::days(days as i64));
    let mut stmt = conn
        .prepare(
            "SELECT DISTINCT currency FROM balance_history WHERE timestamp >= ?1 ORDER BY currency",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params![cutoff], |row| row.get(0))
        .map_err(|e| e.to_string())?;
    let mut currencies = Vec::new();
    for row in rows {
        currencies.push(row.map_err(|e| e.to_string())?);
    }
    Ok(currencies)
}

fn prune_balance_history(retention_days: u64) -> Result<(), String> {
    let conn = open_history_db()?;
    let cutoff = format_time(Local::now() - ChronoDuration::days(retention_days as i64));
    conn.execute(
        "DELETE FROM balance_history WHERE timestamp < ?1",
        params![cutoff],
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

fn open_history_db() -> Result<Connection, String> {
    ensure_dir(&state_dir().map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let path = db_file().map_err(|e| e.to_string())?;
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
    let Ok(marker) = db_marker_file() else {
        return;
    };
    if marker.exists() && !path.exists() {
        let message = format!(
            "SQLite database is missing: {}. A new database will be created; balance history and API keys stored only in SQLite may be lost.",
            path.display()
        );
        eprintln!("{message}");
        log_line(&message).ok();
    }
}

fn mark_database_initialized() -> std::io::Result<()> {
    let marker = db_marker_file()?;
    if !marker.exists() {
        fs::write(marker, "1\n")?;
    }
    Ok(())
}

fn prune_logs_on_startup(config: &AppConfig) -> std::io::Result<()> {
    ensure_dir(&state_dir()?)?;
    prune_log_file(&log_file()?, config.retention_days)
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

fn config_dir() -> std::io::Result<PathBuf> {
    Ok(std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .unwrap_or(home_dir()?.join(".config"))
        .join(APP_DIR))
}

fn state_dir() -> std::io::Result<PathBuf> {
    Ok(std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .unwrap_or(home_dir()?.join(".local").join("state"))
        .join(APP_DIR))
}

fn config_file() -> std::io::Result<PathBuf> {
    Ok(config_dir()?.join("config.json"))
}

fn log_file() -> std::io::Result<PathBuf> {
    Ok(state_dir()?.join("app.log"))
}

fn db_file() -> std::io::Result<PathBuf> {
    Ok(state_dir()?.join("balance_history.db"))
}

fn db_marker_file() -> std::io::Result<PathBuf> {
    Ok(state_dir()?.join(".balance_history.db.initialized"))
}

fn secure_key_file() -> std::io::Result<PathBuf> {
    Ok(state_dir()?.join(".secure_settings.key"))
}

fn history_export_file(export_path: &str) -> std::io::Result<PathBuf> {
    let dir = if export_path.trim().is_empty() {
        home_dir()?
    } else {
        PathBuf::from(export_path.trim())
    };
    Ok(dir.join(history_export_filename()))
}

fn history_export_filename() -> String {
    format!(
        "deepseek-balance-history-{}.csv",
        Local::now().format("%Y%m%d")
    )
}

fn home_dir() -> std::io::Result<PathBuf> {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .ok_or_else(|| std::io::Error::new(std::io::ErrorKind::NotFound, "HOME is not set"))
}

fn ensure_dir(path: &Path) -> std::io::Result<()> {
    fs::create_dir_all(path)
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

fn format_time(value: DateTime<Local>) -> String {
    value.format("%Y-%m-%d %H:%M:%S").to_string()
}

fn default_interval() -> u64 {
    10
}

fn default_threshold() -> f64 {
    1.0
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

fn default_currency() -> String {
    "CNY".to_string()
}

fn fail(error: impl ToString) -> (i32, String) {
    (1, error.to_string())
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
    fn formats_status_and_balance_helpers() {
        assert_eq!(parse_amount("12.34"), 12.34);
        assert_eq!(parse_amount("bad"), 0.0);
        assert_eq!(format_amount(1.2), "1.20");
        assert_eq!(format_signed_amount(2.0), "+2.00");
        assert_eq!(normalize_service_status("major_outage"), "critical");
        assert!(status_rank("critical") > status_rank("major"));
        assert_eq!(
            service_status_notification_label("none"),
            "🟢 All Systems Operational"
        );
        let now = Local::now();
        assert_eq!(
            relative_time_en(now - ChronoDuration::minutes(5), now),
            "5 minutes ago"
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
                .busy_hours_left,
            1_919_810.0
        );
        assert!(demo::history(&conn, 24).expect("demo history loads").len() > 1);

        let mut balances = BTreeMap::new();
        balances.insert("CNY".to_string(), balance(5.0));
        assert!(is_low_balance(&balances, 10.0));
    }

    #[test]
    fn keeps_shared_theme_config_and_qml_widget_contracts() {
        for theme in [
            "default",
            "contrast",
            "bright",
            "dark_mode",
            "mono",
            "custom",
        ] {
            assert_eq!(parse_theme_arg(theme).unwrap(), theme);
        }
        assert!(parse_theme_arg("invalid").is_err());

        let colors = parse_icon_colors(&[
            "#3c6966".to_string(),
            "b9463c".to_string(),
            "78695a".to_string(),
            "69696e".to_string(),
        ])
        .unwrap();
        assert_eq!(colors.get("ok").map(String::as_str), Some("3c6966"));
        assert!(parse_icon_colors(&["bad".to_string()]).is_err());
        let config = AppConfig {
            api_key: API_KEY_MASK.to_string(),
            ..Default::default()
        };
        let json = serde_json::to_string(&ConfigJson {
            config,
            has_key: true,
        })
        .unwrap();
        assert!(json.contains("\"api_key\":\"masked\""));
        assert!(json.contains("\"has_key\":true"));

        let qml = include_str!("../plasmoid/package/contents/ui/main.qml");
        assert!(qml.contains("function estimatedAvailabilityText()"));
        assert!(qml.contains("function rainmeterBalanceLine()"));
        assert!(qml.contains("function relativeLastCheck()"));
        assert!(qml.contains("lines.push(\"💰 \""));
        assert!(qml.contains("lines.push(\"📡 \""));
        assert!(qml.contains("/usr/local/bin/dsmon opencode-go json"));
        assert!(qml.contains("/usr/local/bin/dsmon command-code json"));
        assert!(qml.contains("function applyOpencodeGo"));
        assert!(qml.contains("function applyCommandCode"));
        assert!(qml.contains("function formatCcValue"));
        assert!(qml.contains("function barColor"));
        assert!(qml.contains("function formatOgValue"));
        assert!(qml.contains("ogRollingPercent"));
        assert!(qml.contains("cc5hPercent"));
        assert!(qml.contains("text: \"OpenCode\""));
        assert!(qml.contains("tr(\"ccTitle\")"));
        assert!(!qml.contains("text: tr(\"balances\")"));
        assert!(!qml.contains("model: Object.keys(root.balances)"));

        let config_qml = include_str!("../plasmoid/package/contents/ui/configGeneral.qml");
        assert!(config_qml.contains("id: exportPathField"));
        assert!(config_qml.contains("config.export_path"));
        assert!(config_qml.contains("/usr/local/bin/dsmon set "));
        assert!(!config_qml.contains("set-config"));
        let account_qml = include_str!("../plasmoid/package/contents/ui/configAccount.qml");
        assert!(account_qml.contains("/usr/local/bin/dsmon command-code set-key"));
        assert!(account_qml.contains("/usr/local/bin/dsmon opencode-go set-key"));
        assert!(account_qml.contains("/usr/local/bin/dsmon set-key"));
        assert!(account_qml.contains("ogApiKeyField"));
        assert!(account_qml.contains("ccApiKeyField"));
        assert!(account_qml.contains("groupCredentials"));
        assert!(!account_qml.contains("groupQuota"));
        assert!(!account_qml.contains("QtControls.ProgressBar"));
        assert!(!account_qml.contains("/usr/local/bin/dsmon opencode-go json"));
        let sub_qml = include_str!("../plasmoid/package/contents/ui/configSubscription.qml");
        assert!(sub_qml.contains("/usr/local/bin/dsmon opencode-go json"));
        assert!(sub_qml.contains("/usr/local/bin/dsmon command-code json"));
        assert!(sub_qml.contains("groupOg"));
        assert!(sub_qml.contains("groupCc"));
        assert!(sub_qml.contains("QtControls.ProgressBar"));
        assert!(sub_qml.contains("barColor"));
        assert!(sub_qml.contains("formatOgValue"));
        assert!(sub_qml.contains("formatCcValue"));
        let config_model = include_str!("../plasmoid/package/contents/config/config.qml");
        assert!(config_model.contains("configAccount.qml"));
        assert!(config_model.contains("account"));
        assert!(config_model.contains("configSubscription.qml"));
        assert!(config_model.contains("subscription"));
    }

    #[test]
    fn sets_individual_config_fields_for_cli() {
        let mut config = AppConfig::default();
        assert_eq!(config.language, "en");
        assert!(
            !apply_config_field(&mut config, "export_path", &["/tmp/dsbm".to_string()]).unwrap()
        );
        assert_eq!(config.export_path, "/tmp/dsbm");
        assert!(!apply_config_field(
            &mut config,
            "http-proxy",
            &["http://127.0.0.1:7890".to_string()]
        )
        .unwrap());
        assert_eq!(config.http_proxy, "http://127.0.0.1:7890");
        assert!(!apply_config_field(&mut config, "ui-language", &["zh".to_string()]).unwrap());
        assert_eq!(config.ui_language, "zh");
        assert!(apply_config_field(&mut config, "language", &["zh".to_string()]).is_err());
        assert!(apply_config_field(&mut config, "ui-language", &["fr".to_string()]).is_err());
        assert!(apply_config_field(&mut config, "interval", &["0".to_string()]).is_err());
        assert!(apply_config_field(&mut config, "retention-days", &["3651".to_string()]).is_err());
        assert!(!apply_config_field(&mut config, "theme", &["dark_mode".to_string()]).unwrap());
        assert_eq!(config.theme, "dark_mode");
        assert!(apply_config_field(&mut config, "auto_start", &["true".to_string()]).unwrap());
        assert!(config.auto_start);

        assert!(!apply_config_field(
            &mut config,
            "icon_colors",
            &[
                "3c6966".to_string(),
                "b9463c".to_string(),
                "78695a".to_string(),
                "69696e".to_string(),
            ],
        )
        .unwrap());
        assert_eq!(config.theme, "custom");
        assert_eq!(
            config.icon_colors.get("ok").map(String::as_str),
            Some("3c6966")
        );
        assert!(apply_config_field(&mut config, "api_key", &["demo".to_string()]).is_err());
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
        assert!(is_service_degraded("minor"));
        assert!(!is_service_degraded("unknown"));
        assert_eq!(
            balances_from_history(&records)
                .get("CNY")
                .expect("history balance exists")
                .total_balance,
            7.0
        );
        assert!(history_csv(&records).contains("2026-01-02 00:00:00,CNY,7.00,5.00,2.00,minor"));
        assert_eq!(csv_escape("CNY,\"test\""), "\"CNY,\"\"test\"\"\"");
        assert_eq!(
            history_export_file("/tmp/dsbm-export")
                .unwrap()
                .parent()
                .unwrap(),
            std::path::Path::new("/tmp/dsbm-export")
        );
        assert_eq!(
            history_export_file("")
                .unwrap()
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
        assert_eq!(format_reset_seconds(2_307_600), "26d 17h");
    }

    #[test]
    fn parses_command_code_api_json() {
        // 模拟 /alpha/billing/credits 的真实响应（GOAT 档：5h 14 / 周 35 / 月 70）
        let payload = r#"{
            "credits": {
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
        let monthly_cap = parsed
            .window_limits
            .five_hour
            .as_ref()
            .zip(parsed.window_limits.weekly.as_ref())
            .and_then(|(five_hour, weekly)| command_code_monthly_cap(five_hour.cap, weekly.cap));
        let quota = CommandCodeQuota {
            five_hour: parsed
                .window_limits
                .five_hour
                .map(|window| api_cc_window_to_window(window, now)),
            weekly: parsed
                .window_limits
                .weekly
                .map(|window| api_cc_window_to_window(window, now)),
            monthly: command_code_monthly_window(monthly_cap, parsed.credits.monthly_credits),
        };
        let five_hour = quota.five_hour.expect("five hour window");
        assert_eq!(five_hour.used, 4.2);
        assert_eq!(five_hour.cap, 14.0);
        // 1798761600000 是毫秒时间戳，对应未来某个时间
        assert!(five_hour.reset_in_sec > 0);
        let weekly = quota.weekly.expect("weekly window");
        assert_eq!(weekly.used, 17.5);
        assert_eq!(weekly.cap, 35.0);
        let monthly = quota.monthly.expect("monthly window");
        assert_eq!(monthly.cap, 70.0);
        assert!((monthly.used - 22.0).abs() < 1e-9);
        assert_eq!(monthly.reset_in_sec, 0);

        // 档位映射（官方文档表：5h/周 cap -> 月额度）
        assert_eq!(
            [
                command_code_monthly_cap(3.0, 6.0),
                command_code_monthly_cap(14.0, 35.0),
                command_code_monthly_cap(16.0, 40.0),
                command_code_monthly_cap(45.0, 90.0),
                command_code_monthly_cap(90.0, 180.0),
                command_code_monthly_cap(12.0, 24.0),
            ],
            [
                Some(10.0),
                Some(70.0),
                Some(80.0),
                Some(150.0),
                Some(300.0),
                Some(40.0),
            ]
        );
        // 未收录档位（含无窗口的纯充值账号）不推算月度
        assert_eq!(command_code_monthly_cap(10.0, 20.0), None);
        assert!(command_code_monthly_window(None, Some(48.0)).is_none());
        assert!(command_code_monthly_window(Some(70.0), None).is_none());
        // 月度剩余高于档位（促销加成）时已用夹到 0
        let promo = command_code_monthly_window(Some(70.0), Some(90.0)).expect("promo window");
        assert_eq!(promo.used, 0.0);
        assert_eq!(promo.cap, 70.0);

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
