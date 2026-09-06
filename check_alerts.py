import urllib.request
import json

data = json.loads(urllib.request.urlopen("http://127.0.0.1:8000/api/alerts").read().decode("utf-8"))
print(f"Total alerts recorded: {len(data['alerts'])}")
for a in data['alerts']:
    msg = a['message'].encode('ascii', 'replace').decode('ascii')
    print(f"[{a['alert_type']}] {a['timestamp']} - {msg}")
