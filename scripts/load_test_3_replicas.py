import json
import urllib.request
from collections import Counter

url = "http://emi.local/api/emi"
counts = Counter()
failed = 0

for i in range(1, 31):
    data = json.dumps({
        "principal": 500000,
        "rate": 12,
        "months": 24
    }).encode()

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Connection": "close"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read())
            pod = result["servedBy"]["name"]
            ip = result["servedBy"]["ip"]
            counts[pod] += 1
            print(f"{i:02d}. HTTP {response.status} | {pod} | {ip}")
    except Exception as exc:
        failed += 1
        print(f"{i:02d}. FAILED: {exc}")

print("\n========== LOAD BALANCING SUMMARY ==========")
for pod, count in sorted(counts.items()):
    print(f"{pod}: {count} requests")
print(f"\nTotal successful requests: {sum(counts.values())}")
print(f"Failed requests: {failed}")
