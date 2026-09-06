import urllib.request
import json

data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/top5").read().decode("utf-8"))
print(f"Scan ID: {data['scan_id']}")
print(f"Timestamp: {data['timestamp']}")
print(f"Total flights searched: {data['total_flights_searched']}")
print("\nTOP 5 CHEAPEST FLIGHTS:")
for f in data["top5"]:
    print(f"Rank #{f['rank']}: {f['departure_airport']} -> {f['arrival_airport']} | {f['airline']} {f['flight_number']} | Base: Rs {f['base_fare']} | Taxes/Fees: Rs {round(f['taxes']+f['fees'], 2)} | Baggage: Rs {f['baggage_cost']} | Ground: Rs {f['ground_transport_cost']} | Total: Rs {f['total_effective_price']} | Source: {f['source_name']} ({f['source_type']})")
