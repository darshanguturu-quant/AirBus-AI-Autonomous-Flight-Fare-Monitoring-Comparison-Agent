"""
Database module for persistent state management using SQLite.
Stores user configuration, scan history, flights, price trends, alerts, and source audit logs.
"""
import sqlite3
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from config import MonitorConfig

DB_PATH = os.path.join(os.path.dirname(__file__), "flight_monitor.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables with indexes."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # User Configuration table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_config (
        id INTEGER PRIMARY KEY,
        config_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Scans table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT UNIQUE NOT NULL,
        timestamp TEXT NOT NULL,
        duration_ms INTEGER,
        total_flights_searched INTEGER,
        cheapest_fare REAL,
        top5_json TEXT,
        dates_summary_json TEXT,
        status TEXT NOT NULL
    )
    """)

    # Migration: ensure dates_summary_json column exists if DB already created
    try:
        cursor.execute("ALTER TABLE scans ADD COLUMN dates_summary_json TEXT")
    except Exception:
        pass

    # Flights table (normalized itineraries)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS flights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT NOT NULL,
        itinerary_id TEXT NOT NULL,
        departure_airport TEXT NOT NULL,
        arrival_airport TEXT NOT NULL,
        airline TEXT NOT NULL,
        flight_number TEXT NOT NULL,
        departure_datetime TEXT NOT NULL,
        arrival_datetime TEXT NOT NULL,
        stops INTEGER NOT NULL,
        stopover_airports TEXT,
        duration_minutes INTEGER NOT NULL,
        cabin TEXT NOT NULL,
        base_fare REAL NOT NULL,
        taxes REAL NOT NULL,
        fees REAL NOT NULL,
        baggage_cost REAL NOT NULL,
        baggage_included TEXT,
        airfare_total REAL NOT NULL,
        ground_transport_cost REAL NOT NULL,
        total_effective_price REAL NOT NULL,
        currency TEXT NOT NULL,
        original_currency TEXT,
        original_price REAL,
        source_name TEXT NOT NULL,
        source_domain TEXT NOT NULL,
        source_url TEXT NOT NULL,
        sources_checked_json TEXT,
        source_reliability_score INTEGER NOT NULL,
        source_type TEXT NOT NULL,
        timestamp_checked TEXT NOT NULL,
        availability_status TEXT NOT NULL,
        is_verified INTEGER NOT NULL,
        FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
    )
    """)

    # Price History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        itinerary_id TEXT NOT NULL,
        scan_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        total_effective_price REAL NOT NULL,
        airfare_total REAL NOT NULL,
        source_name TEXT NOT NULL
    )
    """)

    # Alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        itinerary_id TEXT NOT NULL,
        route TEXT NOT NULL,
        airline TEXT NOT NULL,
        previous_price REAL,
        current_price REAL,
        price_difference REAL,
        percentage_change REAL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        is_read INTEGER DEFAULT 0
    )
    """)

    # Source Audit Logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS source_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_domain TEXT NOT NULL,
        is_approved_domain INTEGER NOT NULL,
        status TEXT NOT NULL,
        response_time_ms INTEGER,
        flights_found INTEGER,
        error_message TEXT
    )
    """)

    # Create indexes for fast lookup and time-series queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_flights_scan ON flights(scan_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_flights_itinerary ON flights(itinerary_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_itinerary ON price_history(itinerary_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")

    conn.commit()
    conn.close()


def get_config() -> MonitorConfig:
    """Retrieve saved configuration or initialize with defaults."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT config_json FROM user_config WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if row and row["config_json"]:
        try:
            data = json.loads(row["config_json"])
            if "consecutive_days" not in data or data["consecutive_days"] < 7:
                data["consecutive_days"] = 7
            # Remove obsolete fields: baggage, ground_transport_costs, alert_price_drop_absolute
            data.pop("baggage", None)
            data.pop("ground_transport_costs", None)
            data.pop("alert_price_drop_absolute", None)
            # Remove AUH airport as destination
            if "destination_airports" in data and "AUH" in data["destination_airports"]:
                data["destination_airports"] = [a for a in data["destination_airports"] if a != "AUH"]
            if "destination" in data and "AUH" in data["destination"]:
                data["destination"] = "Dubai (DXB, SHJ)"
            if "prefer_international_airlines" not in data:
                data["prefer_international_airlines"] = True
            valid_keys = MonitorConfig.model_fields.keys()
            filtered_data = {k: v for k, v in data.items() if k in valid_keys}
            cfg = MonitorConfig(**filtered_data)
            save_config(cfg)
            return cfg
        except Exception:
            pass

    # Default fallback
    cfg = MonitorConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: MonitorConfig) -> None:
    """Save user configuration to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    config_json = cfg.model_dump_json()

    cursor.execute("""
    INSERT INTO user_config (id, config_json, updated_at)
    VALUES (1, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        config_json = excluded.config_json,
        updated_at = excluded.updated_at
    """, (config_json, now_str))

    conn.commit()
    conn.close()


def save_scan(
    scan_id: str,
    timestamp: str,
    duration_ms: int,
    total_flights: int,
    cheapest_fare: float,
    top5_list: List[Dict[str, Any]],
    dates_summary: Optional[Dict[str, Any]] = None,
    status: str = "SUCCESS"
) -> None:
    """Record a completed scan."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO scans (scan_id, timestamp, duration_ms, total_flights_searched, cheapest_fare, top5_json, dates_summary_json, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scan_id, timestamp, duration_ms, total_flights, cheapest_fare,
        json.dumps(top5_list),
        json.dumps(dates_summary) if dates_summary else None,
        status
    ))
    conn.commit()
    conn.close()


def save_flights(flights_list: List[Dict[str, Any]]) -> None:
    """Batch insert normalized flights and update price history."""
    if not flights_list:
        return
    conn = get_db_connection()
    cursor = conn.cursor()

    for f in flights_list:
        cursor.execute("""
        INSERT INTO flights (
            scan_id, itinerary_id, departure_airport, arrival_airport, airline,
            flight_number, departure_datetime, arrival_datetime, stops, stopover_airports,
            duration_minutes, cabin, base_fare, taxes, fees, baggage_cost,
            baggage_included, airfare_total, ground_transport_cost, total_effective_price,
            currency, original_currency, original_price, source_name, source_domain,
            source_url, sources_checked_json, source_reliability_score, source_type,
            timestamp_checked, availability_status, is_verified
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """, (
            f["scan_id"], f["itinerary_id"], f["departure_airport"], f["arrival_airport"], f["airline"],
            f["flight_number"], f["departure_datetime"], f["arrival_datetime"], f["stops"], f.get("stopover_airports", ""),
            f["duration_minutes"], f["cabin"], f["base_fare"], f["taxes"], f["fees"], f["baggage_cost"],
            f.get("baggage_included", ""), f["airfare_total"], f["ground_transport_cost"], f["total_effective_price"],
            f["currency"], f.get("original_currency", "INR"), f.get("original_price", f["total_effective_price"]),
            f["source_name"], f["source_domain"], f["source_url"], json.dumps(f.get("sources_checked", [])),
            f["source_reliability_score"], f["source_type"], f["timestamp_checked"], f["availability_status"],
            1 if f.get("is_verified", True) else 0
        ))

        # Also add to price history
        cursor.execute("""
        INSERT INTO price_history (itinerary_id, scan_id, timestamp, total_effective_price, airfare_total, source_name)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            f["itinerary_id"], f["scan_id"], f["timestamp_checked"], f["total_effective_price"],
            f["airfare_total"], f["source_name"]
        ))

    conn.commit()
    conn.close()


def save_alerts(alerts_list: List[Dict[str, Any]]) -> None:
    """Save generated alerts."""
    if not alerts_list:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    for a in alerts_list:
        cursor.execute("""
        INSERT INTO alerts (
            scan_id, alert_type, itinerary_id, route, airline,
            previous_price, current_price, price_difference, percentage_change,
            message, timestamp, is_read
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            a["scan_id"], a["alert_type"], a["itinerary_id"], a["route"], a["airline"],
            a.get("previous_price"), a.get("current_price"), a.get("price_difference"),
            a.get("percentage_change"), a["message"], a["timestamp"]
        ))
    conn.commit()
    conn.close()


def save_audit_logs(logs_list: List[Dict[str, Any]]) -> None:
    """Save source audit logs."""
    if not logs_list:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    for l in logs_list:
        cursor.execute("""
        INSERT INTO source_audit_logs (
            scan_id, timestamp, source_name, source_domain, is_approved_domain,
            status, response_time_ms, flights_found, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            l["scan_id"], l["timestamp"], l["source_name"], l["source_domain"],
            1 if l.get("is_approved_domain", True) else 0, l["status"],
            l.get("response_time_ms", 0), l.get("flights_found", 0), l.get("error_message", "")
        ))
    conn.commit()
    conn.close()


def get_latest_scan() -> Optional[Dict[str, Any]]:
    """Get the most recent scan details with TOP 5."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("top5_json"):
        d["top5"] = json.loads(d["top5_json"])
    else:
        d["top5"] = []
    if d.get("dates_summary_json"):
        d["dates_comparison"] = json.loads(d["dates_summary_json"])
    return d


def get_previous_scan() -> Optional[Dict[str, Any]]:
    """Get the second most recent scan for change comparison."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1 OFFSET 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if d.get("top5_json"):
        d["top5"] = json.loads(d["top5_json"])
    else:
        d["top5"] = []
    if d.get("dates_summary_json"):
        d["dates_comparison"] = json.loads(d["dates_summary_json"])
    return d


def get_all_scans(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent scans."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, scan_id, timestamp, duration_ms, total_flights_searched, cheapest_fare, status FROM scans ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_price_history_for_itinerary(itinerary_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Get price history for a specific flight."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT timestamp, total_effective_price, airfare_total, source_name
    FROM price_history
    WHERE itinerary_id = ?
    ORDER BY id ASC LIMIT ?
    """, (itinerary_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_alerts(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent alerts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_recent_audit_logs(limit: int = 30) -> List[Dict[str, Any]]:
    """Get recent audit logs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM source_audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows
