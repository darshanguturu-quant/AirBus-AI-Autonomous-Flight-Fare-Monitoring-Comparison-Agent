"""
Unit Tests for 3 Consecutive Dates Price Comparison and Cheapest Date Determination.
"""
import pytest
from datetime import datetime, timedelta
from config import MonitorConfig
from engine.normalizer import normalize_flight
from engine.ranking import rank_and_select_top5
from sources.google_flights_live import build_exact_deep_links


def test_consecutive_dates_generation():
    cfg = MonitorConfig(travel_date="2026-09-20", consecutive_days=7)
    dates = cfg.get_consecutive_dates()
    assert len(dates) == 7
    assert dates == [
        "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23",
        "2026-09-24", "2026-09-25", "2026-09-26"
    ]


def test_normalizer_preserves_travel_date():
    cfg = MonitorConfig(travel_date="2026-09-20")
    raw_flight = {
        "itinerary_id": "gf_blr_dxb_indigo_2026-09-21_0800_15000",
        "travel_date": "2026-09-21",
        "departure_airport": "BLR",
        "arrival_airport": "DXB",
        "airline": "IndiGo",
        "flight_number": "6E-1475",
        "departure_datetime": "2026-09-21T08:00:00",
        "arrival_datetime": "2026-09-21T11:00:00",
        "stops": 0,
        "duration_minutes": 240,
        "base_fare": 11250.0,
        "taxes": 2700.0,
        "fees": 1050.0,
        "baggage_cost": 0.0,
        "airfare_total": 15000.0,
        "currency": "INR",
        "source_name": "Google Flights (Live)",
        "source_domain": "google.com",
        "source_url": "https://www.google.com/travel/flights?q=flights%20from%20BLR%20to%20DXB%20on%202026-09-21%20one%20way&curr=INR"
    }

    norm = normalize_flight(raw_flight, cfg)
    assert norm["travel_date"] == "2026-09-21"
    assert norm["total_effective_price"] == 15000.0  # DXB ground transport = 0


def test_deep_links_embed_specific_date():
    links = build_exact_deep_links("BLR", "DXB", "2026-09-22", "IndiGo")
    assert "2026-09-22" in links["google_flights"]
    assert "one%20way" in links["google_flights"]
    assert "curr=INR" in links["google_flights"]
    assert "2026-09-22" in links["airline_direct"]


def test_cheapest_date_determination_and_savings():
    """Simulate 3 consecutive dates and verify cheapest date and savings calculation."""
    flights = [
        # Day 1: 2026-09-20
        {"itinerary_id": "f1", "travel_date": "2026-09-20", "total_effective_price": 18471.0, "airfare_total": 18471.0, "ground_transport_cost": 0.0, "departure_airport": "BLR", "arrival_airport": "DXB", "airline": "IndiGo", "stops": 0, "duration_minutes": 240, "availability_status": "available"},
        # Day 2: 2026-09-21
        {"itinerary_id": "f2", "travel_date": "2026-09-21", "total_effective_price": 15077.0, "airfare_total": 15077.0, "ground_transport_cost": 0.0, "departure_airport": "HYD", "arrival_airport": "SHJ", "airline": "Air Arabia", "stops": 0, "duration_minutes": 230, "availability_status": "available"},
        # Day 3: 2026-09-22
        {"itinerary_id": "f3", "travel_date": "2026-09-22", "total_effective_price": 11953.0, "airfare_total": 11953.0, "ground_transport_cost": 0.0, "departure_airport": "HYD", "arrival_airport": "SHJ", "airline": "Air Arabia", "stops": 0, "duration_minutes": 230, "availability_status": "available"},
    ]

    dates = ["2026-09-20", "2026-09-21", "2026-09-22"]
    cheapest_by_date = {}

    for dt in dates:
        dt_flights = [f for f in flights if f["travel_date"] == dt]
        cheapest_by_date[dt] = min(dt_flights, key=lambda x: x["total_effective_price"])

    prices = [cheapest_by_date[dt]["total_effective_price"] for dt in dates]
    min_price = min(prices)
    max_price = max(prices)
    max_savings = round(max_price - min_price, 2)
    overall_cheapest_date = next(dt for dt in dates if cheapest_by_date[dt]["total_effective_price"] == min_price)

    assert overall_cheapest_date == "2026-09-22"
    assert min_price == 11953.0
    assert max_savings == 18471.0 - 11953.0  # ₹6,518 saved vs Day 1
