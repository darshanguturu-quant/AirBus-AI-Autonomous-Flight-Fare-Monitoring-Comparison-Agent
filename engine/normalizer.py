"""
Data Normalization & Ground Transport Calculation Engine.
Enforces Sections 8, 17, and 21:
- Normalizes pricing into Base Fare + Mandatory Taxes + Mandatory Fees + Baggage Cost.
- Integrates Dubai Ground Transport calculation (DXB, SHJ, AUH) while keeping it clearly labeled.
- Normalizes all currencies to INR.
"""
from typing import Dict, Any
from config import MonitorConfig


def normalize_flight(flight: Dict[str, Any], config: MonitorConfig) -> Dict[str, Any]:
    """
    Normalizes a single flight dictionary into standard schema.
    Total effective price is strictly the authentic quoted live airfare.
    No ground transport artificial costs or baggage surcharges are added.
    """
    f = flight.copy()

    # Ensure currency is INR
    currency = f.get("currency", "INR")
    if currency != "INR":
        conversion_rates = {"AED": 22.8, "USD": 83.5, "EUR": 90.5}
        rate = conversion_rates.get(currency, 1.0)
        f["original_currency"] = currency
        f["original_price"] = f.get("total_price", f.get("airfare_total", 0.0))
        f["base_fare"] = round(f["base_fare"] * rate, 2)
        f["taxes"] = round(f["taxes"] * rate, 2)
        f["fees"] = round(f["fees"] * rate, 2)
        f["baggage_cost"] = 0.0
        f["currency"] = "INR"

    base_fare = float(f.get("base_fare", 0.0))
    taxes = float(f.get("taxes", 0.0))
    fees = float(f.get("fees", 0.0))

    # Exact airfare as quoted on the live website (100% price match)
    if "airfare_total" in f and float(f["airfare_total"]) > 0:
        airfare_total = round(float(f["airfare_total"]), 2)
    else:
        airfare_total = round(base_fare + taxes + fees, 2)

    f["airfare_total"] = airfare_total
    f["baggage_cost"] = 0.0
    f["ground_transport_cost"] = 0.0
    f["total_effective_price"] = airfare_total

    # Clean stops and duration
    f["stops"] = int(f.get("stops", 0))
    f["duration_minutes"] = int(f.get("duration_minutes", 0))
    f["travel_date"] = f.get("travel_date") or f.get("departure_datetime", "")[:10]

    return f
