#!/usr/bin/env python3
"""Capture the missing 3-replica / 100 POST req/s per-pod CPU profile.

Run from ~/projects/emi_milestone1:
    python3 capture_graph2_cpu.py

The script scales emi-web to 3 replicas, verifies readiness, generates 1000
random one-request session templates (httperf session-log limit), requests
6000 sessions at 100 sessions/sec, and samples kubectl top pods every 15s.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import random
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path.cwd()
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"
RATE = 100
DURATION = 60
TOTAL_SESSIONS = RATE * DURATION
TEMPLATE_COUNT = 1000
RUN_ID = "graph2_r3_rate100"
SESSION_FILE = RAW / f"{RUN_ID}.sessions"
RAW_FILE = RAW / f"{RUN_ID}_httperf.txt"
CSV_FILE = RESULTS / f"{RUN_ID}_pod_cpu_memory.csv"

def run(cmd, check=True, capture=False):
    p = subprocess.run(cmd, text=True,
                       stdout=subprocess.PIPE if capture else None,
                       stderr=subprocess.STDOUT if capture else None)
    if check and p.returncode:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return p.stdout if capture else ""

def cpu_to_m(value: str) -> float:
    value = value.strip()
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000.0

def memory_to_mi(value: str) -> float:
    value = value.strip()
    match = re.fullmatch(r"([0-9.]+)(Ki|Mi|Gi|K|M|G)?", value)
    if not match:
        raise ValueError(f"Unknown memory unit: {value}")
    number = float(match.group(1))
    unit = match.group(2) or "Mi"
    factors = {"Ki": 1/1024, "Mi": 1, "Gi": 1024,
               "K": 1/1024, "M": 1, "G": 1024}
    return number * factors[unit]

def main():
    if not (ROOT / "k8s" / "07-emi-ingress.yaml").exists():
        raise SystemExit("Run this from ~/projects/emi_milestone1.")
    RESULTS.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)

    hpa = run(["kubectl", "get", "hpa", "-n", "emi", "-o", "name"],
              check=False, capture=True).strip()
    if hpa:
        raise SystemExit("An HPA is present. This profiling test requires fixed replicas; remove/disable HPA first.")

    print("Scaling emi-web to exactly 3 replicas...")
    run(["kubectl", "scale", "deployment/emi-web", "--replicas=3", "-n", "emi"])
    run(["kubectl", "rollout", "status", "deployment/emi-web", "-n", "emi", "--timeout=180s"])

    pod_json = json.loads(run([
        "kubectl", "get", "pods", "-n", "emi", "-l", "app=emi-web", "-o", "json"
    ], capture=True))
    ready = []
    for pod in pod_json.get("items", []):
        md, st = pod.get("metadata", {}), pod.get("status", {})
        if md.get("deletionTimestamp"):
            continue
        is_ready = any(c.get("type") == "Ready" and c.get("status") == "True"
                       for c in st.get("conditions", []))
        if st.get("phase") == "Running" and is_ready:
            ready.append(md.get("name"))
    if len(ready) != 3:
        raise SystemExit(f"Expected exactly 3 active Ready web pods; found {len(ready)}: {ready}")
    print("Ready web pods:", ", ".join(ready))

    cpu_request_raw = run([
        "kubectl", "get", "deployment", "emi-web", "-n", "emi",
        "-o", "jsonpath={.spec.template.spec.containers[0].resources.requests.cpu}"
    ], capture=True).strip()
    cpu_request_m = cpu_to_m(cpu_request_raw)
    if cpu_request_m <= 0:
        raise SystemExit("Could not read a positive CPU request from the Deployment.")
    print(f"Per-pod CPU request: {cpu_request_raw} ({cpu_request_m:g}m)")

    rng = random.Random(3100)
    with SESSION_FILE.open("w", encoding="utf-8") as f:
        for _ in range(TEMPLATE_COUNT):
            principal = rng.randint(100_000, 2_000_000)
            rate = round(rng.uniform(2.0, 20.0), 2)
            months = rng.choice([6, 12, 18, 24, 36, 48, 60])
            body = json.dumps({"principal": principal, "rate": rate, "months": months},
                              separators=(",", ":"))
            f.write(f"/api/emi method=POST contents='{body}'\n\n")

    headers = ["timestamp", "run_id", "replicas", "target_req_per_sec",
               "pod", "cpu_millicores", "cpu_request_millicores",
               "cpu_utilization_percent", "memory_mib"]
    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(headers)

    stop = threading.Event()
    sample_errors = []
    sample_count = [0]
    sampled_pods = set()

    def sampler():
        next_tick = time.monotonic()
        while not stop.is_set():
            stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            try:
                output = run([
                    "kubectl", "top", "pods", "-n", "emi",
                    "-l", "app=emi-web", "--no-headers"
                ], capture=True)
                rows = []
                for line in output.splitlines():
                    parts = line.split()
                    if len(parts) >= 3:
                        pod, cpu, memory = parts[:3]
                        cpu_m = cpu_to_m(cpu)
                        mem_mi = memory_to_mi(memory)
                        cpu_pct = cpu_m / cpu_request_m * 100.0
                        rows.append([stamp, RUN_ID, 3, RATE, pod,
                                     f"{cpu_m:.1f}", f"{cpu_request_m:.1f}",
                                     f"{cpu_pct:.2f}", f"{mem_mi:.2f}"])
                        sampled_pods.add(pod)
                with CSV_FILE.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
                sample_count[0] += 1
                print(f"CPU sample {sample_count[0]}: {len(rows)} web pods", flush=True)
            except Exception as exc:
                sample_errors.append(f"{stamp}: {exc}")
                print(f"WARNING sampling pods: {exc}", flush=True)
            next_tick += 15
            if stop.wait(max(0, next_tick - time.monotonic())):
                break

    httperf_cmd = [
        "httperf", "--hog",
        "--server=emi.local", "--port=80", "--server-name=emi.local",
        f"--wsesslog={TOTAL_SESSIONS},0,{SESSION_FILE}",
        f"--rate={RATE}", "--timeout=4",
        "--add-header=Content-Type: application/json\\n"
    ]
    print("\nStarting exactly 60 seconds of nominal 100 POST req/s workload.")
    print("Per-pod CPU and memory will be sampled every 15 seconds.")
    with RAW_FILE.open("w", encoding="utf-8") as raw:
        raw.write("COMMAND: " + " ".join(httperf_cmd) + "\n\n")
        raw.flush()
        proc = subprocess.Popen(httperf_cmd, stdout=raw, stderr=subprocess.STDOUT)
        thread = threading.Thread(target=sampler, daemon=True)
        thread.start()
        start = time.monotonic()
        try:
            while proc.poll() is None:
                time.sleep(1)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise
        finally:
            stop.set()
            thread.join(timeout=25)
        elapsed = time.monotonic() - start

    print(f"\nhttperf exit code: {proc.returncode}")
    print(f"Elapsed: {elapsed:.1f} seconds")
    print(f"Pod metric sampling rounds: {sample_count[0]}")
    print(f"Distinct web pods sampled: {len(sampled_pods)}")
    for pod in sorted(sampled_pods):
        print(" ", pod)
    print("CPU profile CSV:", CSV_FILE)
    print("Raw httperf output:", RAW_FILE)
    if sample_errors:
        print("Sampling warnings:")
        print("\n".join(sample_errors))
    if len(sampled_pods) < 3:
        print("WARNING: Fewer than three distinct web pods were sampled. Review CSV.")
    print("\nDo not delete the CSV or raw output; these are Graph 2 source data.")

if __name__ == "__main__":
    main()
