import json
import time
import urllib.request

url = "http://emi.local/api/emi"
success = 0
failed = 0

for i in range(1, 21):
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
            print(f"{i}: HTTP {response.status} | {result['servedBy']['name']}")
            success += 1
    except Exception as exc:
        print(f"{i}: FAILED | {exc}")
        failed += 1

    time.sleep(0.5)

print(f"\nSuccessful: {success}")
print(f"Failed: {failed}")
