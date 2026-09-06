"""
Scheduler & Autonomous Monitoring Coordinator.
Enforces Section 7 & 18:
- Executes autonomous search workflow every 5 minutes (configurable).
- Tracks countdown timer to next execution.
- Orchestrates: Search -> Normalize -> Deduplicate -> Rank -> Detect Changes -> Save State -> Alert.
- Handles source timeouts and errors gracefully without aborting the loop.
"""
import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable

from config import MonitorConfig
import database as db
from sources.flight_engine import FlightSearchOrchestrator
from engine.normalizer import normalize_flight
from engine.deduplicator import deduplicate_flights
from engine.ranking import rank_and_select_top5
from engine.alerts import detect_price_changes_and_alerts


class MonitoringAgent:
    def __init__(self):
        self.orchestrator = FlightSearchOrchestrator()
        self.is_running = False
        self.is_scanning = False
        self.last_scan_time: Optional[datetime] = None
        self.next_scan_time: Optional[datetime] = None
        self.listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._task: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()

    def register_listener(self, callback: Callable[[Dict[str, Any]], None]):
        """Register subscriber for live scan updates (WebSockets / SSE)."""
        if callback not in self.listeners:
            self.listeners.append(callback)

    def unregister_listener(self, callback: Callable[[Dict[str, Any]], None]):
        if callback in self.listeners:
            self.listeners.remove(callback)

    async def _notify_listeners(self, event_type: str, data: Any):
        for cb in list(self.listeners):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb({"type": event_type, "data": data})
                else:
                    cb({"type": event_type, "data": data})
            except Exception as e:
                print(f"[Notifier Error] {e}")

    async def execute_scan(self, is_manual: bool = False) -> Dict[str, Any]:
        """
        Executes full flight monitoring workflow:
        1. Query approved flight sources.
        2. Normalize data and compute total effective cost.
        3. Deduplicate across sources.
        4. Rank and select Top 5.
        5. Detect price drops and trigger alerts.
        6. Persist results in SQLite.
        """
        async with self.lock:
            self.is_scanning = True
            await self._notify_listeners("SCAN_STARTED", {"is_manual": is_manual, "timestamp": datetime.now().isoformat()})

            scan_id = f"scan_{uuid.uuid4().hex[:10]}"
            timestamp_str = datetime.now().isoformat()
            start_t = time.time()

            try:
                # 1. Fetch current configuration
                config: MonitorConfig = db.get_config()

                # 2. Query Approved Sources via Search Orchestrator
                # Run CPU-bound/simulated network query in thread pool to not block asyncio event loop
                loop = asyncio.get_running_loop()
                raw_flights, audit_logs = await loop.run_in_executor(
                    None, self.orchestrator.search_all_approved_sources, config, scan_id
                )

                # 3. Normalize all flights (base fare + taxes + baggage + Dubai ground transport)
                normalized = [normalize_flight(f, config) for f in raw_flights]

                # 4. Deduplicate matching itineraries across sources
                deduped = deduplicate_flights(normalized)

                # 5. Build 3-consecutive-dates comparison matrix & select TOP 5
                consecutive_dates = config.get_consecutive_dates() if hasattr(config, "get_consecutive_dates") else [config.travel_date]
                cheapest_by_date = {}
                top5_by_date = {}

                for dt in consecutive_dates:
                    dt_flights = [f for f in deduped if f.get("travel_date") == dt or f.get("departure_datetime", "").startswith(dt)]
                    dt_top5 = rank_and_select_top5(dt_flights, config)
                    top5_by_date[dt] = dt_top5
                    cheapest_dt = dt_top5[0] if dt_top5 else None
                    if cheapest_dt:
                        cheapest_by_date[dt] = {
                            "travel_date": dt,
                            "has_flights": True,
                            "price": cheapest_dt["total_effective_price"],
                            "airfare": cheapest_dt["airfare_total"],
                            "ground": cheapest_dt["ground_transport_cost"],
                            "departure_airport": cheapest_dt["departure_airport"],
                            "arrival_airport": cheapest_dt["arrival_airport"],
                            "route": f"{cheapest_dt['departure_airport']} ➔ {cheapest_dt['arrival_airport']}",
                            "airline": cheapest_dt["airline"],
                            "flight_number": cheapest_dt.get("flight_number", ""),
                            "stops": cheapest_dt.get("stops", 0),
                            "duration_minutes": cheapest_dt.get("duration_minutes", 0),
                            "departure_time": cheapest_dt.get("departure_datetime", "")[11:16] if len(cheapest_dt.get("departure_datetime", "")) >= 16 else "",
                            "deep_link": cheapest_dt["source_url"],
                            "deep_links": cheapest_dt.get("deep_links", {}),
                            "flight": cheapest_dt
                        }
                    else:
                        cheapest_by_date[dt] = {
                            "travel_date": dt,
                            "has_flights": False,
                            "price": None,
                            "airfare": None,
                            "ground": None,
                            "route": "No flights found",
                            "airline": "",
                            "deep_link": f"https://www.google.com/travel/flights?q=flights+from+South+India+to+Dubai+on+{dt}+one+way&curr=INR"
                        }

                # Find overall cheapest date and calculate savings
                valid_prices = [cheapest_by_date[dt]["price"] for dt in consecutive_dates if cheapest_by_date[dt]["has_flights"]]
                if valid_prices:
                    min_price = min(valid_prices)
                    max_price = max(valid_prices)
                    max_savings = round(max_price - min_price, 2)
                    overall_cheapest_date = next(dt for dt in consecutive_dates if cheapest_by_date[dt].get("price") == min_price)
                else:
                    min_price = 0.0
                    max_savings = 0.0
                    overall_cheapest_date = consecutive_dates[0] if consecutive_dates else config.travel_date

                dates_comparison = {
                    "consecutive_dates": consecutive_dates,
                    "cheapest_by_date": cheapest_by_date,
                    "overall_cheapest_date": overall_cheapest_date,
                    "overall_cheapest_price": min_price,
                    "max_savings": max_savings,
                    "top5_by_date": top5_by_date
                }

                # Overall TOP 5 cheapest realistic itineraries across all monitored dates
                top5 = rank_and_select_top5(deduped, config)

                # 6. Fetch previous scan from persistent database for change detection
                prev_scan = db.get_latest_scan()
                prev_top5 = prev_scan.get("top5") if prev_scan else None

                # 7. Price Change Detection & Alerts
                alerts = detect_price_changes_and_alerts(top5, prev_top5, config, scan_id)

                # 8. Persist into SQLite
                elapsed_ms = int((time.time() - start_t) * 1000)
                cheapest_fare = top5[0]["total_effective_price"] if top5 else 0.0

                db.save_scan(
                    scan_id=scan_id,
                    timestamp=timestamp_str,
                    duration_ms=elapsed_ms,
                    total_flights=len(deduped),
                    cheapest_fare=cheapest_fare,
                    top5_list=top5,
                    dates_summary=dates_comparison,
                    status="SUCCESS"
                )

                # Save all normalized flights for this scan
                db.save_flights(deduped)

                # Save alerts
                if alerts:
                    db.save_alerts(alerts)

                # Save source audit logs
                if audit_logs:
                    db.save_audit_logs(audit_logs)

                self.last_scan_time = datetime.now()
                self.next_scan_time = self.last_scan_time + timedelta(seconds=config.refresh_interval_seconds)

                scan_result = {
                    "scan_id": scan_id,
                    "timestamp": timestamp_str,
                    "duration_ms": elapsed_ms,
                    "total_flights_searched": len(deduped),
                    "cheapest_fare": cheapest_fare,
                    "top5": top5,
                    "dates_comparison": dates_comparison,
                    "alerts": alerts,
                    "audit_logs": audit_logs[:10],
                    "status": "SUCCESS"
                }

                await self._notify_listeners("SCAN_COMPLETED", scan_result)
                return scan_result

            except Exception as e:
                import traceback
                print(f"[Monitoring Error] {e}\n{traceback.format_exc()}")
                elapsed_ms = int((time.time() - start_t) * 1000)
                db.save_scan(
                    scan_id=scan_id,
                    timestamp=timestamp_str,
                    duration_ms=elapsed_ms,
                    total_flights=0,
                    cheapest_fare=0.0,
                    top5_list=[],
                    status=f"FAILED: {str(e)}"
                )
                err_data = {"scan_id": scan_id, "error": str(e), "status": "FAILED"}
                await self._notify_listeners("SCAN_FAILED", err_data)
                return err_data

            finally:
                self.is_scanning = False

    async def start_autonomous_loop(self):
        """Continuous background loop executing every refresh_interval_seconds (default 5 minutes)."""
        self.is_running = True
        print("[Agent Scheduler] Starting autonomous 5-minute flight monitoring loop...")

        # Run initial scan immediately if database has no scans yet
        existing_scan = db.get_latest_scan()
        if not existing_scan:
            await self.execute_scan()

        while self.is_running:
            config = db.get_config()
            interval = config.refresh_interval_seconds if config.refresh_interval_seconds >= 60 else 300

            # Countdown loop emitting tick every second so frontend stays updated
            for remaining in range(interval, 0, -1):
                if not self.is_running:
                    break
                await self._notify_listeners("TIMER_TICK", {
                    "seconds_remaining": remaining,
                    "total_interval": interval,
                    "is_scanning": self.is_scanning
                })
                await asyncio.sleep(1)

            if self.is_running and config.auto_refresh_enabled:
                print(f"[Agent Scheduler] Triggering scheduled 5-minute scan at {datetime.now().isoformat()}...")
                await self.execute_scan()

    def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()


# Singleton monitoring agent instance
agent = MonitoringAgent()
