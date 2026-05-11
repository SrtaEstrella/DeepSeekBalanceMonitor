use chrono::{Duration as ChronoDuration, Local};
use rusqlite::{params, Connection};
use std::collections::BTreeMap;

use super::{Balance, ConsumptionRate, HistoryRecord};

const API_KEY: &str = "demo";
const CURRENCY: &str = "CNY";
const TOTAL: f64 = 666.0;
const TOPPED: f64 = 114_514.0;
const GRANTED: f64 = 1_919_810.0;
const DAILY_RATE: f64 = 114_514.0;
const HOURS_LEFT: f64 = 1_919_810.0;
const SNAPSHOTS: &[(i64, f64, f64, f64, &str)] = &[
    (240, 1_919_810.0, 114_514.0, 1_805_296.0, "none"),
    (180, 1_145_140.0, 114_514.0, 1_030_626.0, "none"),
    (120, 666_666.0, 114_514.0, 552_152.0, "minor"),
    (60, 114_514.0, 66_600.0, 47_914.0, "none"),
    (0, TOTAL, TOPPED, GRANTED, "none"),
];

pub(super) fn is_enabled(api_key: &str) -> bool {
    api_key.trim().eq_ignore_ascii_case(API_KEY)
}

pub(super) fn prepare(conn: &Connection) -> Result<(), String> {
    conn.execute("DROP TABLE IF EXISTS demo_mode_balance", [])
        .map_err(|e| e.to_string())?;
    conn.execute(
        "CREATE TABLE IF NOT EXISTS demo_mode_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            total REAL NOT NULL,
            topped REAL NOT NULL,
            granted REAL NOT NULL,
            daily_rate REAL NOT NULL,
            hours_left REAL NOT NULL,
            service_status TEXT NOT NULL
        )",
        [],
    )
    .map_err(|e| e.to_string())?;
    for (minutes_ago, total, topped, granted, service_status) in SNAPSHOTS {
        conn.execute(
            "INSERT INTO demo_mode_balance
             (currency, timestamp, total, topped, granted, daily_rate, hours_left, service_status)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
            params![
                CURRENCY,
                (Local::now() - ChronoDuration::minutes(*minutes_ago))
                    .format("%Y-%m-%d %H:%M:%S")
                    .to_string(),
                total,
                topped,
                granted,
                DAILY_RATE,
                HOURS_LEFT,
                service_status
            ],
        )
        .map_err(|e| e.to_string())?;
    }
    Ok(())
}

pub(super) fn balances(conn: &Connection) -> Result<BTreeMap<String, Balance>, String> {
    let mut stmt = conn
        .prepare(
            "SELECT currency, total, topped, granted
             FROM demo_mode_balance
             WHERE timestamp = (SELECT MAX(timestamp) FROM demo_mode_balance)
             ORDER BY currency",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                Balance {
                    total_balance: row.get(1)?,
                    topped_up_balance: row.get(2)?,
                    granted_balance: row.get(3)?,
                },
            ))
        })
        .map_err(|e| e.to_string())?;
    let mut balances = BTreeMap::new();
    for row in rows {
        let (currency, balance) = row.map_err(|e| e.to_string())?;
        balances.insert(currency, balance);
    }
    Ok(balances)
}

pub(super) fn consumption_rate(conn: &Connection) -> Result<ConsumptionRate, String> {
    conn.query_row(
        "SELECT currency, daily_rate, hours_left FROM demo_mode_balance LIMIT 1",
        [],
        |row| {
            Ok(ConsumptionRate {
                currency: row.get(0)?,
                daily_rate: row.get(1)?,
                hours_left: row.get(2)?,
            })
        },
    )
    .map_err(|e| e.to_string())
}

pub(super) fn history(conn: &Connection, limit: usize) -> Result<Vec<HistoryRecord>, String> {
    let limit = i64::try_from(limit).unwrap_or(i64::MAX);
    let mut stmt = conn
        .prepare(
            "SELECT timestamp, currency, total, topped, granted, service_status
             FROM demo_mode_balance
             ORDER BY timestamp ASC
             LIMIT ?1",
        )
        .map_err(|e| e.to_string())?;
    let rows = stmt
        .query_map(params![limit], |row| {
            Ok(HistoryRecord {
                timestamp: row.get(0)?,
                currency: row.get(1)?,
                total: row.get(2)?,
                topped: row.get(3)?,
                granted: row.get(4)?,
                service_status: row.get(5)?,
            })
        })
        .map_err(|e| e.to_string())?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row.map_err(|e| e.to_string())?);
    }
    Ok(records)
}
