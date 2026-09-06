"""
Deduplication Engine.
Enforces Section 10 of specifications:
- Identifies matching itineraries across multiple approved flight websites.
- Consolidates quotes, selects the lowest verified price.
- Preserves all source URLs and records cross-source verification count.
- Resolves ties using Source Reliability hierarchy: Official Airline > Flight Search > Travel OTA.
"""
from typing import List, Dict, Any


def deduplicate_flights(flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicates flight records based on canonical itinerary key:
    (departure, arrival, date, airline, flight_number, departure_time, stops)
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for f in flights:
        itinerary_id = f["itinerary_id"]
        if itinerary_id not in grouped:
            grouped[itinerary_id] = []
        grouped[itinerary_id].append(f)

    deduped_results: List[Dict[str, Any]] = []

    for itinerary_id, candidates in grouped.items():
        if len(candidates) == 1:
            deduped_results.append(candidates[0])
            continue

        # Sort candidates to find the winner:
        # Primary: Lowest total_effective_price
        # Secondary: Highest source_reliability_score (Official Airline > Metasearch > OTA)
        candidates.sort(key=lambda x: (
            x["total_effective_price"],
            -x.get("source_reliability_score", 0)
        ))

        winner = candidates[0].copy()

        # Collect all checked sources
        sources_checked = []
        seen_domains = set()
        for c in candidates:
            domain = c.get("source_domain", "")
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                sources_checked.append({
                    "name": c.get("source_name", domain),
                    "domain": domain,
                    "price": c.get("total_effective_price"),
                    "airfare_total": c.get("airfare_total"),
                    "url": c.get("source_url", "")
                })

        winner["sources_checked"] = sources_checked
        winner["source_count"] = len(sources_checked)

        deduped_results.append(winner)

    return deduped_results
