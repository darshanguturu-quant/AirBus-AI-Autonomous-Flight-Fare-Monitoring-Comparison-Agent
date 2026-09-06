"""
FastAPI Main Application & REST/SSE Server.
Serves real-time flight monitoring API, WebSocket/SSE streams, and UI dashboard.
"""
import os
import json
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import database as db
from config import MonitorConfig, SOUTH_INDIA_AIRPORTS, DESTINATION_AIRPORTS, APPROVED_SOURCES
from scheduler import agent

# Lifespan event to start DB and background scheduler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    db.init_db()
    # Start autonomous flight monitoring loop in background
    scan_task = asyncio.create_task(agent.start_autonomous_loop())
    yield
    # Graceful shutdown
    agent.stop()
    scan_task.cancel()
    try:
        await scan_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="South India to Dubai Autonomous Flight Monitor",
    description="Continuously monitors the 5 cheapest economy flight options from 15 South Indian airports to DXB and SHJ with primary focus on International Airlines and total effective cost normalization.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    # Prevent browser caching of HTML, JS, and CSS files during development and live scans
    if request.url.path.endswith((".js", ".css", ".html")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount static folder
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=FileResponse)
async def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Flight Monitor initializing...</h1>", status_code=200)
    return FileResponse(index_path)


@app.get("/api/status")
async def get_agent_status():
    latest_scan = db.get_latest_scan()
    all_scans = db.get_all_scans(limit=1)
    cfg = db.get_config()

    return {
        "is_running": agent.is_running,
        "is_scanning": agent.is_scanning,
        "last_scan_time": latest_scan["timestamp"] if latest_scan else None,
        "refresh_interval_seconds": cfg.refresh_interval_seconds,
        "total_scans_recorded": len(db.get_all_scans(limit=100)),
        "current_cheapest_fare": latest_scan["cheapest_fare"] if latest_scan else None
    }


@app.get("/api/top5")
async def get_top5_flights():
    """Returns the latest TOP 5 cheapest realistic itineraries and 3 consecutive dates comparison."""
    latest_scan = db.get_latest_scan()
    if not latest_scan or not latest_scan.get("top5"):
        # If no scan has completed yet, run one immediately
        scan_res = await agent.execute_scan(is_manual=True)
        return {
            "scan_id": scan_res.get("scan_id"),
            "timestamp": scan_res.get("timestamp"),
            "top5": scan_res.get("top5", []),
            "dates_comparison": scan_res.get("dates_comparison"),
            "total_flights_searched": scan_res.get("total_flights_searched", 0)
        }

    return {
        "scan_id": latest_scan["scan_id"],
        "timestamp": latest_scan["timestamp"],
        "duration_ms": latest_scan.get("duration_ms", 0),
        "total_flights_searched": latest_scan.get("total_flights_searched", 0),
        "cheapest_fare": latest_scan.get("cheapest_fare", 0),
        "top5": latest_scan.get("top5", []),
        "dates_comparison": latest_scan.get("dates_comparison")
    }


@app.get("/api/dates-comparison")
async def get_dates_comparison():
    """Returns the 3 consecutive dates price matrix and cheapest date determination."""
    latest_scan = db.get_latest_scan()
    if not latest_scan or not latest_scan.get("dates_comparison"):
        scan_res = await agent.execute_scan(is_manual=True)
        return scan_res.get("dates_comparison", {})
    return latest_scan.get("dates_comparison", {})


@app.post("/api/scan")
async def trigger_manual_scan():
    """Forces an immediate fresh search across all approved sources."""
    if agent.is_scanning:
        return {"status": "ALREADY_SCANNING", "message": "A scan is currently running in background."}
    result = await agent.execute_scan(is_manual=True)
    return {"status": "SUCCESS", "data": result}


@app.get("/api/config")
async def get_configuration():
    """Returns user configuration and metadata for all 15 departure airports and Dubai destinations."""
    cfg = db.get_config()
    return {
        "config": cfg.model_dump(),
        "available_departure_airports": SOUTH_INDIA_AIRPORTS,
        "available_destination_airports": DESTINATION_AIRPORTS,
        "approved_sources": APPROVED_SOURCES
    }


@app.post("/api/config")
async def update_configuration(new_cfg: MonitorConfig):
    """Updates user configuration without modifying code."""
    db.save_config(new_cfg)
    # Trigger a scan with updated parameters
    asyncio.create_task(agent.execute_scan(is_manual=True))
    return {"status": "UPDATED", "config": new_cfg.model_dump()}


@app.get("/api/history")
async def get_price_history(itinerary_id: str = ""):
    """Returns price trend history for a specific flight or general recent scans."""
    if itinerary_id:
        history = db.get_price_history_for_itinerary(itinerary_id)
        return {"itinerary_id": itinerary_id, "history": history}

    scans = db.get_all_scans(limit=25)
    return {"scans": scans}


@app.get("/api/alerts")
async def get_alerts():
    """Returns recent price drop and entrant alerts."""
    alerts = db.get_recent_alerts(limit=30)
    return {"alerts": alerts}


@app.get("/api/audit-logs")
async def get_source_audit_logs():
    """Returns source audit logs showing approved domain compliance and response metrics."""
    logs = db.get_recent_audit_logs(limit=40)
    return {
        "logs": logs,
        "approved_domains": list(APPROVED_SOURCES.keys())
    }


@app.get("/api/events")
async def stream_live_events(request: Request):
    """
    Server-Sent Events (SSE) stream for real-time timer countdown,
    instant scan completion events, and audio alert dispatches.
    """
    queue: asyncio.Queue = asyncio.Queue()

    def listener(event):
        try:
            queue.put_nowait(event)
        except Exception:
            pass

    agent.register_listener(listener)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    data_str = json.dumps(event)
                    yield f"event: message\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping
                    yield ": ping\n\n"
        finally:
            agent.unregister_listener(listener)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
