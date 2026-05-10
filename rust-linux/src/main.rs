use chrono::{DateTime, Duration as ChronoDuration, Local, NaiveDateTime};
use reqwest::StatusCode;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process;
use std::thread;
use std::time::Duration;

const APP_DIR: &str = "deepseek-balance-monitor";
const HISTORY_DEDUP_SECONDS: i64 = 120;

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
    records: Vec<HistoryRecord>,
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
    language: String,
    ui_language: String,
    last_check: String,
    total_currency: Option<String>,
    total_balance: Option<f64>,
    low_balance: bool,
    service_status: String,
    service_degraded: bool,
    history: Vec<HistoryRecord>,
    balances: BTreeMap<String, Balance>,
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

#[derive(Deserialize, Default)]
struct StatusInfo {
    #[serde(default)]
    indicator: String,
}

#[derive(Deserialize)]
struct StatusPayload {
    #[serde(default)]
    status: StatusInfo,
}

#[derive(Deserialize)]
struct ComponentsPayload {
    #[serde(default)]
    components: Vec<ComponentStatus>,
}

#[derive(Deserialize)]
struct ComponentStatus {
    #[serde(default)]
    name: String,
    #[serde(default)]
    status: String,
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
        "set-config" => set_config(&args[2..]),
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
    let service_status = fetch_service_status();
    let key = config.api_key.trim();
    if key.is_empty() {
        ensure_config_file().map_err(fail)?;
        print_status(
            None,
            Some("DeepSeek API key is not configured."),
            checked_at,
            &service_status,
        );
        return Err((2, String::new()));
    }
    let api_key = key.chars().filter(|c| c.is_ascii()).collect::<String>();
    match fetch_balance(&api_key) {
        Ok(balances) => {
            save_balance_history(&balances).map_err(fail)?;
            print_status(Some(&balances), None, checked_at, &service_status);
            log_line("Balance check succeeded").map_err(fail)?;
            Ok(())
        }
        Err(error) => {
            print_status(None, Some(&error), checked_at, &service_status);
            log_line(&format!("Balance check failed: {error}")).ok();
            Err((1, String::new()))
        }
    }
}

fn run_daemon() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    prune_logs_on_startup(&config).map_err(fail)?;
    prune_balance_history(config.retention_days).map_err(fail)?;
    let api_key = require_api_key(&config)?;
    let interval = Duration::from_secs(config.interval_minutes.clamp(1, 1440) * 60);
    let mut low_balance_reported = false;
    let mut last_service_status = fetch_service_status();
    log_line("dsmon daemon started").map_err(fail)?;
    loop {
        let service_status = fetch_service_status();
        if service_status != last_service_status {
            log_line(&format!(
                "DeepSeek API status changed: {}",
                service_status_label(&service_status)
            ))
            .ok();
            if config.api_alert_enabled {
                eprintln!(
                    "DeepSeek API Status: {}",
                    service_status_label(&service_status)
                );
            }
            last_service_status = service_status;
        }
        match fetch_balance(&api_key) {
            Ok(balances) => {
                if let Err(error) = save_balance_history(&balances) {
                    log_line(&format!("Failed to save balance history: {error}")).ok();
                }
                log_line(&format!("Balance check succeeded: {}", summary(&balances))).ok();
                let low_balance = is_low_balance(&balances, config.threshold_yuan);
                if low_balance {
                    log_line("Balance is below configured threshold").ok();
                    if should_low_balance_alert(&config, &mut low_balance_reported) {
                        eprintln!("{}", low_balance_message(&balances, config.threshold_yuan));
                    }
                } else {
                    low_balance_reported = false;
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
        "Usage: dsmon [check|daemon|init-config|config-path|log-path|clean-logs|history|widget-status|config-json|set-config]\nHistory: dsmon history [days] | dsmon history export [days] [currency|all] [path|-]"
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
                "DeepSeek API key is not configured.\nEdit config file: {}\nSet api_key to your DeepSeek API key.",
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
    let history = recent_balance_history(config.retention_days, 5).unwrap_or_default();
    let checked_at = Local::now();
    let service_status = fetch_service_status();
    let service_degraded = service_status != "none";
    let key = config.api_key.trim();
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
            language: config.language.clone(),
            ui_language: config.ui_language.clone(),
            last_check: format_time(checked_at),
            total_currency: None,
            total_balance: None,
            low_balance: false,
            service_status,
            service_degraded,
            history,
            balances: BTreeMap::new(),
        });
    }
    let api_key = key.chars().filter(|c| c.is_ascii()).collect::<String>();
    match fetch_balance(&api_key) {
        Ok(balances) => {
            save_balance_history(&balances).map_err(fail)?;
            let (total_currency, total_balance) = preferred_balance(&balances)
                .map(|(currency, balance)| (Some(currency.clone()), Some(balance.total_balance)))
                .unwrap_or((None, None));
            let history = recent_balance_history(config.retention_days, 5).unwrap_or_default();
            write_widget_status(WidgetStatus {
                ok: true,
                configured: true,
                error: None,
                config_path,
                interval_minutes: config.interval_minutes,
                threshold_yuan: config.threshold_yuan,
                api_alert_enabled: config.api_alert_enabled,
                retention_days: config.retention_days,
                language: config.language.clone(),
                ui_language: config.ui_language.clone(),
                last_check: format_time(checked_at),
                total_currency,
                total_balance,
                low_balance: is_low_balance(&balances, config.threshold_yuan),
                service_status: service_status.clone(),
                service_degraded,
                history,
                balances,
            })
        }
        Err(error) => write_widget_status(WidgetStatus {
            ok: false,
            configured: true,
            error: Some(error),
            config_path,
            interval_minutes: config.interval_minutes,
            threshold_yuan: config.threshold_yuan,
            api_alert_enabled: config.api_alert_enabled,
            retention_days: config.retention_days,
            language: config.language.clone(),
            ui_language: config.ui_language.clone(),
            last_check: format_time(checked_at),
            total_currency: None,
            total_balance: None,
            low_balance: false,
            service_status,
            service_degraded,
            history,
            balances: BTreeMap::new(),
        }),
    }
}

fn write_widget_status(status: WidgetStatus) -> Result<(), (i32, String)> {
    let text = serde_json::to_string(&status).map_err(fail)?;
    println!("{text}");
    Ok(())
}

fn print_config_json() -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    println!("{}", serde_json::to_string(&config).map_err(fail)?);
    Ok(())
}

fn print_history(args: &[String]) -> Result<(), (i32, String)> {
    let config = load_config().map_err(fail)?;
    match args.first().map(String::as_str) {
        Some("export") => export_history(&args[1..], config.retention_days),
        Some("json") => print_history_json(&args[1..], config.retention_days),
        _ => print_history_summary(args, config.retention_days),
    }
}

fn print_history_summary(args: &[String], default_days: u64) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), default_days)?;
    let report = history_report(days, None, usize::MAX).map_err(fail)?;
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

fn print_history_json(args: &[String], default_days: u64) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), default_days)?;
    let currency = history_currency(args.get(1));
    let report = history_report(days, currency.as_deref(), 500).map_err(fail)?;
    println!("{}", serde_json::to_string(&report).map_err(fail)?);
    Ok(())
}

fn export_history(args: &[String], default_days: u64) -> Result<(), (i32, String)> {
    let days = parse_history_days(args.first(), default_days)?;
    let currency = history_currency(args.get(1));
    let records = history_records(days, currency.as_deref(), usize::MAX).map_err(fail)?;
    let csv = history_csv(&records);
    match args.get(2).map(String::as_str) {
        Some("-") => print!("{csv}"),
        path => {
            let path = path
                .map(PathBuf::from)
                .map(Ok)
                .unwrap_or_else(history_export_file)
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
) -> Result<HistoryReport, String> {
    let records = history_records(days, currency, limit)?;
    Ok(HistoryReport {
        days,
        currency: currency.unwrap_or("all").to_string(),
        currencies: history_currencies(days)?,
        total_records: records.len(),
        summary: summarize_history(&records),
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

fn history_csv(records: &[HistoryRecord]) -> String {
    let mut lines = vec!["timestamp,currency,total,topped,granted".to_string()];
    for record in records {
        lines.push(format!(
            "{},{},{},{},{}",
            csv_escape(&record.timestamp),
            csv_escape(&record.currency),
            format_amount(record.total),
            format_amount(record.topped),
            format_amount(record.granted)
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

fn set_config(args: &[String]) -> Result<(), (i32, String)> {
    if args.len() != 7 && args.len() != 8 {
        return Err(fail(
            "Usage: dsmon set-config <api_key> <interval_minutes> <threshold_yuan> <ui_language> <auto_start> <alert_mode> [api_alert_enabled] <retention_days>",
        ));
    }
    let api_key = args[0].trim().to_string();
    if api_key.is_empty() {
        return Err((2, "DeepSeek API key is required.".to_string()));
    }
    let threshold_yuan = args[2].parse::<f64>().map_err(fail)?;
    if !(0.0..=10000.0).contains(&threshold_yuan) {
        return Err(fail("Balance threshold must be between 0 and 10000."));
    }
    let mut config = load_config().unwrap_or_default();
    config.api_key = api_key;
    config.interval_minutes = args[1].parse::<u64>().map_err(fail)?.clamp(1, 1440);
    config.threshold_yuan = threshold_yuan;
    config.language = default_lang();
    config.ui_language = if args[3] == "zh" { "zh" } else { "en" }.to_string();
    config.auto_start = parse_bool_arg(&args[4]).map_err(fail)?;
    config.alert_mode = parse_alert_mode_arg(&args[5]).map_err(fail)?;
    if args.len() == 8 {
        config.api_alert_enabled = parse_bool_arg(&args[6]).map_err(fail)?;
    }
    let retention_arg = if args.len() == 8 { &args[7] } else { &args[6] };
    config.retention_days = retention_arg.parse::<u64>().map_err(fail)?.clamp(1, 3650);
    normalize_config(&mut config);
    save_config(&config).map_err(fail)?;
    set_auto_start(config.auto_start).map_err(fail)?;
    println!("Config saved.");
    Ok(())
}

fn fetch_balance(api_key: &str) -> Result<BTreeMap<String, Balance>, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?;
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

fn fetch_service_status() -> String {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
    else {
        return "unknown".to_string();
    };
    let mut status = fetch_overall_status(&client).unwrap_or("unknown");
    if let Some(api_status) = fetch_api_component_status(&client) {
        if status_rank(api_status) > status_rank(status) {
            status = api_status;
        }
    }
    status.to_string()
}

fn fetch_overall_status(client: &reqwest::blocking::Client) -> Option<&'static str> {
    let payload: StatusPayload = client
        .get("https://status.deepseek.com/api/v2/status.json")
        .header("Accept", "application/json")
        .send()
        .ok()?
        .error_for_status()
        .ok()?
        .json()
        .ok()?;
    Some(normalize_service_status(&payload.status.indicator))
}

fn fetch_api_component_status(client: &reqwest::blocking::Client) -> Option<&'static str> {
    let payload: ComponentsPayload = client
        .get("https://status.deepseek.com/api/v2/components.json")
        .header("Accept", "application/json")
        .send()
        .ok()?
        .error_for_status()
        .ok()?
        .json()
        .ok()?;
    payload
        .components
        .into_iter()
        .filter(|item| item.name.to_ascii_lowercase().contains("api"))
        .map(|item| normalize_service_status(&item.status))
        .max_by_key(|status| status_rank(status))
}

fn print_status(
    balances: Option<&BTreeMap<String, Balance>>,
    error: Option<&str>,
    checked_at: DateTime<Local>,
    service_status: &str,
) {
    println!("DeepSeek Balance:");
    if let Some((currency, balance)) = balances.and_then(|items| preferred_balance(items)) {
        println!(
            "{} {} (Topped {}, Granted {})",
            format_amount(balance.total_balance),
            currency,
            format_amount(balance.topped_up_balance),
            format_amount(balance.granted_balance)
        );
        println!("Last Check: {}", format_time(checked_at));
    } else if let Some(error) = error {
        println!("Query error: {error}");
    } else {
        println!("Not checked");
    }
    println!(
        "DeepSeek API Status: {}",
        service_status_label(service_status)
    );
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
    balances.iter().next()
}

fn normalize_service_status(value: &str) -> &'static str {
    match value {
        "none" | "operational" => "none",
        "minor" | "degraded_performance" => "minor",
        "major" | "partial_outage" => "major",
        "critical" | "major_outage" => "critical",
        "maintenance" | "under_maintenance" => "maintenance",
        _ => "unknown",
    }
}

fn status_rank(status: &str) -> u8 {
    match status {
        "none" => 0,
        "maintenance" => 1,
        "minor" => 2,
        "major" => 3,
        "critical" => 4,
        _ => 5,
    }
}

fn service_status_label(status: &str) -> &'static str {
    match status {
        "none" => "🟢 All Systems Operational",
        "minor" => "🟡 Minor Outage",
        "major" => "🟠 Major Outage",
        "critical" => "🔴 Critical Outage",
        "maintenance" => "🔧 Under Maintenance",
        _ => "⚪ Status Unknown",
    }
}

fn is_low_balance(balances: &BTreeMap<String, Balance>, threshold: f64) -> bool {
    preferred_balance(balances)
        .map(|(_, balance)| balance.total_balance < threshold)
        .unwrap_or(false)
}

fn low_balance_message(balances: &BTreeMap<String, Balance>, threshold: f64) -> String {
    if let Some((currency, balance)) = preferred_balance(balances) {
        format!(
            "⚠ DeepSeek Low Balance\nBalance is only {} {}, below your alert threshold of {} {}.\nPlease top up!",
            format_amount(balance.total_balance),
            currency,
            format_amount(threshold),
            currency
        )
    } else {
        "⚠ DeepSeek Low Balance\nNo balance information is available.".to_string()
    }
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

fn should_low_balance_alert(config: &AppConfig, reported: &mut bool) -> bool {
    match config.alert_mode.as_str() {
        "never" => false,
        "always" => true,
        _ if *reported => false,
        _ => {
            *reported = true;
            true
        }
    }
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
    let previous_language = config.language.clone();
    let previous_ui_language = config.ui_language.clone();
    let missing_ui_language = !text.contains("\"ui_language\"");
    normalize_config(&mut config);
    if missing_ui_language
        || previous_language != config.language
        || previous_ui_language != config.ui_language
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
}

fn save_config(config: &AppConfig) -> std::io::Result<()> {
    ensure_dir(&config_dir()?)?;
    let file = File::create(config_file()?)?;
    serde_json::to_writer_pretty(file, config)?;
    Ok(())
}

fn ensure_config_file() -> std::io::Result<()> {
    if !config_file()?.exists() {
        save_config(&AppConfig::default())?;
    }
    Ok(())
}

fn log_line(message: &str) -> std::io::Result<()> {
    ensure_dir(&state_dir()?)?;
    let path = log_file()?;
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(file, "[{}] {}", format_time(Local::now()), message)
}

fn save_balance_history(balances: &BTreeMap<String, Balance>) -> Result<(), String> {
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
            "INSERT INTO balance_history (timestamp, currency, total, topped, granted) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                &timestamp,
                currency.as_str(),
                balance.total_balance,
                balance.topped_up_balance,
                balance.granted_balance
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
    let cutoff = format_time(Local::now() - ChronoDuration::days(days as i64));
    let limit = i64::try_from(limit).unwrap_or(i64::MAX);
    let mut stmt;
    let rows = if let Some(currency) = currency {
        stmt = conn
            .prepare(
                "SELECT timestamp, currency, total, topped, granted FROM balance_history \
                 WHERE timestamp >= ?1 AND currency = ?2 ORDER BY timestamp ASC LIMIT ?3",
            )
            .map_err(|e| e.to_string())?;
        stmt.query_map(params![cutoff, currency, limit], history_record_from_row)
            .map_err(|e| e.to_string())?
    } else {
        stmt = conn
            .prepare(
                "SELECT timestamp, currency, total, topped, granted FROM balance_history \
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
    let conn =
        Connection::open(db_file().map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    conn.execute(
        "CREATE TABLE IF NOT EXISTS balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            currency TEXT NOT NULL,
            total REAL NOT NULL,
            topped REAL NOT NULL,
            granted REAL NOT NULL
        )",
        [],
    )
    .map_err(|e| e.to_string())?;
    Ok(conn)
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

fn history_export_file() -> std::io::Result<PathBuf> {
    let documents = home_dir()?.join("Documents");
    let dir = if documents.exists() {
        documents
    } else {
        state_dir()?
    };
    Ok(dir.join("deepseek-balance-history.csv"))
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
    let locale = ["LC_ALL", "LC_MESSAGES", "LANG"]
        .iter()
        .filter_map(|key| std::env::var(key).ok())
        .map(|value| value.trim().to_string())
        .find(|value| !value.is_empty());
    match locale {
        Some(value) if value.to_ascii_lowercase().starts_with("zh") => "zh".to_string(),
        Some(_) => "en".to_string(),
        None => "zh".to_string(),
    }
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
    fn formats_status_and_alerts_low_balance_once() {
        assert_eq!(parse_amount("12.34"), 12.34);
        assert_eq!(parse_amount("bad"), 0.0);
        assert_eq!(format_amount(1.2), "1.20");
        assert_eq!(format_signed_amount(2.0), "+2.00");
        assert_eq!(normalize_service_status("major_outage"), "critical");
        assert!(status_rank("critical") > status_rank("major"));

        let mut balances = BTreeMap::new();
        balances.insert("CNY".to_string(), balance(5.0));
        assert!(is_low_balance(&balances, 10.0));
        assert!(low_balance_message(&balances, 10.0).contains("5.00 CNY"));

        let mut config = AppConfig::default();
        let mut reported = false;
        assert!(should_low_balance_alert(&config, &mut reported));
        assert!(!should_low_balance_alert(&config, &mut reported));
        config.alert_mode = "never".to_string();
        assert!(!should_low_balance_alert(&config, &mut false));
        config.alert_mode = "always".to_string();
        assert!(should_low_balance_alert(&config, &mut true));
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
            },
            HistoryRecord {
                timestamp: "2026-01-02 00:00:00".to_string(),
                currency: "CNY".to_string(),
                total: 7.0,
                topped: 5.0,
                granted: 2.0,
            },
        ];
        let summary = summarize_history(&records);
        assert_eq!(summary[0].records, 2);
        assert_eq!(summary[0].latest_total, 7.0);
        assert_eq!(summary[0].change_total, -3.0);
        assert!(history_csv(&records).contains("2026-01-02 00:00:00,CNY,7.00,5.00,2.00"));
        assert_eq!(csv_escape("CNY,\"test\""), "\"CNY,\"\"test\"\"\"");

        let cutoff =
            NaiveDateTime::parse_from_str("2026-01-02 00:00:00", "%Y-%m-%d %H:%M:%S").unwrap();
        assert!(!keep_log_line("[2026-01-01 23:59:59] old", cutoff));
        assert!(keep_log_line("[2026-01-02 00:00:00] keep", cutoff));
        assert!(keep_log_line("unstructured line", cutoff));
    }
}
