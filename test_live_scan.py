from fast_flights import create_query, FlightQuery, get_flights
from datetime import datetime, timedelta

q_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
print(f"Testing Real Live Queries for travel date: {q_date}\n")

airports = ['COK', 'CCJ', 'CNN', 'TRV', 'MAA', 'BLR', 'HYD', 'IXE', 'TRZ', 'CJB']
destinations = ['SHJ', 'DXB', 'AUH']

all_found = []
for dep in airports:
    for arr in destinations:
        try:
            q = create_query(
                flights=[FlightQuery(date=q_date, from_airport=dep, to_airport=arr)],
                seat='economy',
                trip='one-way',
                currency='INR'
            )
            res = get_flights(q)
            if res:
                for f in res:
                    if f.price and f.price > 0:
                        airline = f.airlines[0] if f.airlines else "Unknown"
                        stops = len(f.flights) - 1
                        all_found.append({
                            "dep": dep,
                            "arr": arr,
                            "price": f.price,
                            "airline": airline,
                            "stops": stops
                        })
                        print(f"Found: {dep} -> {arr} | Rs {f.price} | {airline} | stops: {stops}")
        except Exception as e:
            print(f"Error for {dep} -> {arr}: {e}")

print(f"\nTotal real flights found: {len(all_found)}")
if all_found:
    all_found.sort(key=lambda x: x["price"])
    print("\nCHEAPEST 5 REAL OPTIONS:")
    for idx, item in enumerate(all_found[:5]):
        print(f"#{idx+1}: {item['dep']} -> {item['arr']} | Rs {item['price']} | {item['airline']} | stops: {item['stops']}")
