"""
Unit and Integration Tests for Flight Fare Monitoring & Comparison Agent.
Tests:
- Strict Source Allowlist & Domain Validation
- Price Normalization & Dubai Ground Transport Calculation
- Deduplication & Cross-Source Price Merging
- TOP 5 Cheapest Effective Fare Ranking Algorithm
- Price Drop & Entrant Alert Logic
"""
import pytest
from config import MonitorConfig
from sources.allowlist import validate_and_classify_source, is_strictly_disallowed, extract_domain
from engine.normalizer import normalize_flight
from engine.deduplicator import deduplicate_flights
from engine.ranking import rank_and_select_top5
from engine.alerts import detect_price_changes_and_alerts


def test_domain_extractor():
    assert extract_domain("https://www.google.com/travel/flights") == "google.com"
    assert extract_domain("https://goindigo.in/booking") == "goindigo.in"
    assert extract_domain("flights.google.com") == "flights.google.com"
    assert extract_domain("http://airarabia.com:80/flights") == "airarabia.com"


def test_allowlist_approved_sources():
    # Official airlines
    approved, meta = validate_and_classify_source("https://www.goindigo.in")
    assert approved is True
    assert meta["type"] == "Official Airline"
    assert meta["reliability"] == 100

    approved, meta = validate_and_classify_source("https://www.airarabia.com")
    assert approved is True
    assert meta["type"] == "Official Airline"

    # Flight search metasearch
    approved, meta = validate_and_classify_source("https://www.google.com/travel/flights")
    assert approved is True
    assert meta["type"] == "Verified Flight Search"
    assert meta["reliability"] == 80

    approved, meta = validate_and_classify_source("https://www.skyscanner.net")
    assert approved is True

    # Travel OTA
    approved, meta = validate_and_classify_source("https://www.makemytrip.com")
    assert approved is True
    assert meta["type"] == "Travel OTA"


def test_allowlist_blocks_disallowed_sources():
    # Strict blocks on social media, blogs, forums
    assert is_strictly_disallowed("https://reddit.com/r/travel") is True
    assert is_strictly_disallowed("https://www.facebook.com/groups/travel") is True
    assert is_strictly_disallowed("https://twitter.com/cheapflights") is True

    # Validate function returns False for unapproved
    approved, _ = validate_and_classify_source("https://reddit.com/r/deals")
    assert approved is False

    approved, _ = validate_and_classify_source("https://some-random-blog.com/cheap-fares")
    assert approved is False


def test_price_normalization_and_ground_transport():
    cfg = MonitorConfig()
    cfg.ground_transport_costs = {"DXB": 0.0, "SHJ": 500.0}

    # Flight 1: to DXB
    raw_dxb = {
        "itinerary_id": "flight_dxb_1",
        "arrival_airport": "DXB",
        "base_fare": 6000.0,
        "taxes": 1800.0,
        "fees": 400.0,
        "baggage_cost": 0.0,
        "currency": "INR"
    }
    norm_dxb = normalize_flight(raw_dxb, cfg)
    assert norm_dxb["airfare_total"] == 8200.0
    assert norm_dxb["ground_transport_cost"] == 0.0
    assert norm_dxb["total_effective_price"] == 8200.0

    # Flight 2: to SHJ (Sharjah) with ₹500 ground transport
    raw_shj = {
        "itinerary_id": "flight_shj_1",
        "arrival_airport": "SHJ",
        "base_fare": 5500.0,
        "taxes": 1600.0,
        "fees": 400.0,
        "baggage_cost": 0.0,
        "currency": "INR"
    }
    norm_shj = normalize_flight(raw_shj, cfg)
    assert norm_shj["airfare_total"] == 7500.0
    assert norm_shj["ground_transport_cost"] == 500.0
    assert norm_shj["total_effective_price"] == 8000.0

    # Notice: Even with ₹500 ground transport, SHJ (₹8000) is cheaper than DXB (₹8200)!
    assert norm_shj["total_effective_price"] < norm_dxb["total_effective_price"]


def test_deduplication():
    # Same itinerary quoted on two different websites:
    # 1. Official Airline quoting ₹7,500
    # 2. Metasearch quoting ₹7,700
    itinerary_id = "canonical_coimbatore_shj_001"
    flight_airline = {
        "itinerary_id": itinerary_id,
        "departure_airport": "CJB",
        "arrival_airport": "SHJ",
        "airline": "Air Arabia",
        "flight_number": "G9 414",
        "total_effective_price": 7500.0,
        "airfare_total": 7000.0,
        "source_name": "Air Arabia Official",
        "source_domain": "airarabia.com",
        "source_url": "https://www.airarabia.com",
        "source_reliability_score": 100,
        "availability_status": "available"
    }
    flight_meta = {
        "itinerary_id": itinerary_id,
        "departure_airport": "CJB",
        "arrival_airport": "SHJ",
        "airline": "Air Arabia",
        "flight_number": "G9 414",
        "total_effective_price": 7700.0,
        "airfare_total": 7200.0,
        "source_name": "Skyscanner",
        "source_domain": "skyscanner.net",
        "source_url": "https://www.skyscanner.net",
        "source_reliability_score": 80,
        "availability_status": "available"
    }

    deduped = deduplicate_flights([flight_airline, flight_meta])
    assert len(deduped) == 1
    winner = deduped[0]
    assert winner["total_effective_price"] == 7500.0
    assert winner["source_name"] == "Air Arabia Official"
    assert winner["source_count"] == 2


def test_ranking_top5_and_constraints():
    cfg = MonitorConfig()
    cfg.maximum_stops = 1
    cfg.maximum_journey_duration_hours = 12

    flights = [
        {"itinerary_id": "f1", "departure_airport": "COK", "arrival_airport": "SHJ", "total_effective_price": 7400.0, "stops": 0, "duration_minutes": 250, "availability_status": "available"},
        {"itinerary_id": "f2", "departure_airport": "CCJ", "arrival_airport": "SHJ", "total_effective_price": 7100.0, "stops": 0, "duration_minutes": 240, "availability_status": "available"},
        {"itinerary_id": "f3", "departure_airport": "BLR", "arrival_airport": "SHJ", "total_effective_price": 7900.0, "stops": 0, "duration_minutes": 255, "availability_status": "available"},
        {"itinerary_id": "f4", "departure_airport": "MAA", "arrival_airport": "DXB", "total_effective_price": 8100.0, "stops": 0, "duration_minutes": 270, "availability_status": "available"},
        {"itinerary_id": "f5", "departure_airport": "HYD", "arrival_airport": "DXB", "total_effective_price": 8300.0, "stops": 0, "duration_minutes": 255, "availability_status": "available"},
        {"itinerary_id": "f6_expensive", "departure_airport": "BLR", "arrival_airport": "DXB", "total_effective_price": 12500.0, "stops": 0, "duration_minutes": 255, "availability_status": "available"},
        {"itinerary_id": "f7_too_many_stops", "departure_airport": "TIR", "arrival_airport": "DXB", "total_effective_price": 6500.0, "stops": 2, "duration_minutes": 300, "availability_status": "available"},
    ]

    top5 = rank_and_select_top5(flights, cfg)
    assert len(top5) == 5

    # Filtered out f7 because maximum_stops is 1
    assert all(f["itinerary_id"] != "f7_too_many_stops" for f in top5)

    # #1 rank should be CCJ at ₹7,100
    assert top5[0]["itinerary_id"] == "f2"
    assert top5[0]["rank"] == 1


def test_alert_logic():
    cfg = MonitorConfig(alert_price_drop_absolute=300.0, alert_price_drop_percentage=5.0)

    # Previous scan top 1
    prev_top5 = [
        {"itinerary_id": "f_prev_1", "departure_airport": "BLR", "arrival_airport": "SHJ", "airline": "Air Arabia", "total_effective_price": 8120.0, "stops": 0, "rank": 1}
    ]

    # Current scan top 1 has a brand new cheaper flight (Condition A)
    curr_top5_new_cheapest = [
        {"itinerary_id": "f_new_1", "departure_airport": "COK", "arrival_airport": "SHJ", "airline": "Air India Express", "total_effective_price": 7450.0, "stops": 0, "rank": 1}
    ]
    alerts_a = detect_price_changes_and_alerts(curr_top5_new_cheapest, prev_top5, cfg, "scan_test_1")
    assert any(a["alert_type"] == "NEW_CHEAPEST" for a in alerts_a)

    # Existing cheapest fare drops by ₹670 (Condition B)
    curr_top5_drop = [
        {"itinerary_id": "f_prev_1", "departure_airport": "BLR", "arrival_airport": "SHJ", "airline": "Air Arabia", "total_effective_price": 7450.0, "stops": 0, "rank": 1}
    ]
    alerts_b = detect_price_changes_and_alerts(curr_top5_drop, prev_top5, cfg, "scan_test_2")
    assert any(a["alert_type"] == "PRICE_DROP" for a in alerts_b)


def test_international_airlines_prioritization():
    from config import is_international_airline

    assert is_international_airline("Emirates") is True
    assert is_international_airline("Air Arabia") is True
    assert is_international_airline("flydubai") is True
    assert is_international_airline("Oman Air") is True
    assert is_international_airline("IndiGo") is False
    assert is_international_airline("Air India Express") is False
    assert is_international_airline("SpiceJet") is False

    cfg = MonitorConfig(prefer_international_airlines=True)
    flights = [
        {"itinerary_id": "f_indigo", "airline": "IndiGo", "departure_airport": "COK", "arrival_airport": "DXB", "total_effective_price": 18000.0, "stops": 0, "duration_minutes": 240, "availability_status": "available"},
        {"itinerary_id": "f_arabia", "airline": "Air Arabia", "departure_airport": "COK", "arrival_airport": "SHJ", "total_effective_price": 21000.0, "stops": 0, "duration_minutes": 240, "availability_status": "available"},
        {"itinerary_id": "f_emirates", "airline": "Emirates", "departure_airport": "BLR", "arrival_airport": "DXB", "total_effective_price": 24000.0, "stops": 0, "duration_minutes": 240, "availability_status": "available"},
        {"itinerary_id": "f_flydubai", "airline": "flydubai", "departure_airport": "CCJ", "arrival_airport": "DXB", "total_effective_price": 22000.0, "stops": 0, "duration_minutes": 240, "availability_status": "available"},
    ]

    ranked = rank_and_select_top5(flights, cfg)
    # International airlines must rank ahead of IndiGo even if IndiGo has a lower base price
    assert ranked[0]["airline"] == "Air Arabia"
    assert ranked[1]["airline"] == "flydubai"
    assert ranked[2]["airline"] == "Emirates"
    assert ranked[3]["airline"] == "IndiGo"

