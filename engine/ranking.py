"""
Ranking Engine.
Enforces Section 11 & Section 4 of specifications:
- Filters invalid or unavailable flights.
- Filters by user constraints: maximum stops, maximum duration, departure airports.
- Ranks strictly by lowest verified total effective cost (Airfare + Dubai Ground Transport Differential).
- Applies tie-breaking & small delta preference for nonstop flights when price delta is negligible.
- Returns TOP 5 results.
"""
from typing import List, Dict, Any
from config import MonitorConfig


def rank_and_select_top5(flights: List[Dict[str, Any]], config: MonitorConfig) -> List[Dict[str, Any]]:
    """
    Filters and ranks flight options to produce the TOP 5 cheapest realistic itineraries.
    """
    valid_flights = []

    for f in flights:
        # 1. Remove invalid results
        if not f.get("itinerary_id") or not f.get("total_effective_price") or f["total_effective_price"] <= 0:
            continue

        # 2. Remove unavailable flights
        if f.get("availability_status") != "available":
            continue

        # 3. User constraint: Departure airport filter
        if config.departure_airports and f.get("departure_airport") not in config.departure_airports:
            continue

        # 4. User constraint: Destination airport filter
        if config.destination_airports and f.get("arrival_airport") not in config.destination_airports:
            continue

        # 5. User constraint: Maximum stops
        if f.get("stops", 0) > config.maximum_stops:
            continue

        # 6. User constraint: Maximum journey duration
        max_duration_mins = config.maximum_journey_duration_hours * 60
        if f.get("duration_minutes", 0) > max_duration_mins:
            continue

        valid_flights.append(f)

    # Ranking formula:
    # Primary: Total Effective Price
    # Nonstop slight bonus: If a nonstop flight is within ₹150 of a 1-stop, prioritize nonstop
    def sort_key(item: Dict[str, Any]):
        price = item["total_effective_price"]
        stops = item.get("stops", 0)
        # Small nonstop tie-breaker if price within ₹150
        effective_rank_score = price - (150.0 if stops == 0 else 0.0)
        reliability = -item.get("source_reliability_score", 0)
        return (effective_rank_score, item["duration_minutes"], reliability)

    valid_flights.sort(key=sort_key)

    top5 = valid_flights[:config.number_of_results]

    # Assign rank numbers (1 to 5)
    for idx, flight in enumerate(top5):
        flight["rank"] = idx + 1

    return top5
