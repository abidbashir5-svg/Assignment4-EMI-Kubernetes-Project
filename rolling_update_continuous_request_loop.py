import json
import time
import urllib.request
from collections import Counter

counts = Counter()
failed = 0
total = 0
url = "http://emi.local/api/emi"

print("Continuous request test started. Press Ctrl+C after rollback.")

try:
    while True:
        total += 1
        data = json.dumps({
            "principal": 500000,
            "rate": 12,
            "months": 24
        }).encode()

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read())
                pod = result["servedBy"]["name"]
                counts[pod] += 1
                print(f"{total}: HTTP {response.status} | {pod}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"{total}: FAILED | {exc}", flush=True)

        time.sleep(1)

except KeyboardInterrupt:
    print("\n===== REQUEST SUMMARY =====")
    print("Total:", total)
    print("Successful:", sum(counts.values()))
    print("Failed:", failed)
