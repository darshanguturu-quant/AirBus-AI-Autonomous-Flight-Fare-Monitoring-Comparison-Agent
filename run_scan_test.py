import asyncio
import database as db
from scheduler import agent

db.init_db()
print("Executing live scan across South Indian airports...")
res = asyncio.run(agent.execute_scan())

print(f"Status: {res.get('status')}")
print(f"Total flights searched: {res.get('total_flights_searched')}")
print(f"Cheapest fare: Rs {res.get('cheapest_fare')}")

print("\n--- TOP 5 VERIFIED REAL FLIGHTS ---")
for f in res.get('top5', []):
    print(f"Rank #{f['rank']}: {f['departure_airport']} -> {f['arrival_airport']} | {f['airline']} {f['flight_number']}")
    print(f"  Live Airfare: Rs {f['airfare_total']} (Exact website price)")
    print(f"  Ground Transport: Rs {f['ground_transport_cost']}")
    print(f"  Total Effective: Rs {f['total_effective_price']}")
    print(f"  Booking Link: {f['source_url']}\n")
