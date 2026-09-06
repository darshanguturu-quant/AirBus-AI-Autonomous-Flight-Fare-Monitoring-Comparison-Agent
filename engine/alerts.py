"""
Price Change Detection & Alert Engine.
Enforces Sections 12 & 14 of specifications:
- Tracks historical price shifts across 5-minute scans.
- Suppresses repetitive/trivial notifications.
- Triggers prominent alerts on:
  A. New absolute cheapest flight appears
  B. Existing cheapest fare drops significantly (default >= ₹300 or >= 5%)
  C. A flight enters the TOP 5
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import MonitorConfig


def detect_price_changes_and_alerts(
    current_top5: List[Dict[str, Any]],
    previous_top5: Optional[List[Dict[str, Any]]],
    config: MonitorConfig,
    scan_id: str
) -> List[Dict[str, Any]]:
    """
    Compares current scan against previous scan and triggers meaningful alerts.
    """
    alerts: List[Dict[str, Any]] = []
    now_str = datetime.now().isoformat()

    if not current_top5:
        return alerts

    current_cheapest = current_top5[0]

    # Map previous scan itineraries
    prev_map: Dict[str, Dict[str, Any]] = {}
    prev_cheapest: Optional[Dict[str, Any]] = None
    prev_top5_ids = set()

    if previous_top5 and len(previous_top5) > 0:
        prev_cheapest = previous_top5[0]
        for idx, f in enumerate(previous_top5):
            it_id = f["itinerary_id"]
            prev_map[it_id] = f
            prev_top5_ids.add(it_id)

    # Calculate delta for each flight in current TOP 5
    for flight in current_top5:
        it_id = flight["itinerary_id"]
        curr_price = flight["total_effective_price"]
        prev_f = prev_map.get(it_id)

        if prev_f:
            old_price = prev_f["total_effective_price"]
            diff = round(curr_price - old_price, 2)
            pct = round((diff / old_price) * 100, 2) if old_price > 0 else 0.0

            flight["previous_price"] = old_price
            flight["price_difference"] = diff
            flight["percentage_change"] = pct
            flight["price_trend"] = "down" if diff < 0 else ("up" if diff > 0 else "steady")
        else:
            flight["previous_price"] = None
            flight["price_difference"] = 0.0
            flight["percentage_change"] = 0.0
            flight["price_trend"] = "new"

    # If this is the very first scan, record initial state without noisy alerts
    if not prev_cheapest:
        return alerts

    # --- Condition A: New cheapest flight appears ---
    prev_lowest_price = prev_cheapest["total_effective_price"]
    curr_lowest_price = current_cheapest["total_effective_price"]

    if current_cheapest["itinerary_id"] != prev_cheapest["itinerary_id"] and curr_lowest_price < prev_lowest_price:
        drop_amount = round(prev_lowest_price - curr_lowest_price, 2)
        pct_drop = round((drop_amount / prev_lowest_price) * 100, 2)
        alerts.append({
            "scan_id": scan_id,
            "alert_type": "NEW_CHEAPEST",
            "itinerary_id": current_cheapest["itinerary_id"],
            "route": f"{current_cheapest['departure_airport']} → {current_cheapest['arrival_airport']}",
            "airline": current_cheapest["airline"],
            "previous_price": prev_lowest_price,
            "current_price": curr_lowest_price,
            "price_difference": -drop_amount,
            "percentage_change": -pct_drop,
            "message": (
                f"🚨 NEW CHEAPEST FARE: {current_cheapest['departure_airport']} → {current_cheapest['arrival_airport']} "
                f"at ₹{curr_lowest_price:,.0f} ({current_cheapest['airline']}, {current_cheapest['stops']} stops). "
                f"Previous lowest was ₹{prev_lowest_price:,.0f} (Dropped by ₹{drop_amount:,.0f} / {pct_drop}%)."
            ),
            "timestamp": now_str
        })

    # --- Condition B: Existing cheapest fare drops significantly (>= ₹300 or >= 5%) ---
    elif current_cheapest["itinerary_id"] == prev_cheapest["itinerary_id"]:
        drop_amount = round(prev_lowest_price - curr_lowest_price, 2)
        pct_drop = round((drop_amount / prev_lowest_price) * 100, 2) if prev_lowest_price > 0 else 0.0

        if drop_amount >= config.alert_price_drop_absolute or pct_drop >= config.alert_price_drop_percentage:
            alerts.append({
                "scan_id": scan_id,
                "alert_type": "PRICE_DROP",
                "itinerary_id": current_cheapest["itinerary_id"],
                "route": f"{current_cheapest['departure_airport']} → {current_cheapest['arrival_airport']}",
                "airline": current_cheapest["airline"],
                "previous_price": prev_lowest_price,
                "current_price": curr_lowest_price,
                "price_difference": -drop_amount,
                "percentage_change": -pct_drop,
                "message": (
                    f"📉 SIGNIFICANT PRICE DROP on #1 Fare: {current_cheapest['departure_airport']} → {current_cheapest['arrival_airport']} "
                    f"dropped by ₹{drop_amount:,.0f} ({pct_drop}%) from ₹{prev_lowest_price:,.0f} to ₹{curr_lowest_price:,.0f}."
                ),
                "timestamp": now_str
            })

    # --- Condition C: A new flight enters the TOP 5 ---
    for flight in current_top5:
        it_id = flight["itinerary_id"]
        if it_id not in prev_top5_ids:
            alerts.append({
                "scan_id": scan_id,
                "alert_type": "ENTERED_TOP_5",
                "itinerary_id": it_id,
                "route": f"{flight['departure_airport']} → {flight['arrival_airport']}",
                "airline": flight["airline"],
                "previous_price": None,
                "current_price": flight["total_effective_price"],
                "price_difference": None,
                "percentage_change": None,
                "message": (
                    f"⭐ NEW ENTRANT IN TOP 5: {flight['departure_airport']} → {flight['arrival_airport']} "
                    f"({flight['airline']}) ranked #{flight.get('rank')} at ₹{flight['total_effective_price']:,.0f}."
                ),
                "timestamp": now_str
            })

    return alerts
