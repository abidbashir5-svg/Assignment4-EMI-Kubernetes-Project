#!/usr/bin/env python3
"""
Run the 15 fixed-replica Milestone 4 experiments:
  replicas = 1, 2, 3
  rates = 10, 25, 50, 100, 200 POST requests/sec
  duration = 60 seconds per experiment

Each httperf session contains exactly one POST /api/emi request, so httperf's
--rate (sessions/sec when --wsesslog is used) is also the request rate.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path.cwd()
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"
DURATION = 60
RATES = [10, 25, 50, 100, 200]
REPLICAS = [1, 2, 3]

SUMMARY_CSV = RESULTS / "fixed_replica_summary.csv"
POD_CSV = RESULTS / "per_pod_metrics.csv"
HOST_CSV = RESULTS / "host_cpu_metrics.csv"
COMPLETED_FILE = RESULTS / "fixed_replica_completed.txt"


def require_command(name: str) -> None:
    from shutil import which
    if which(name) is None:
        raise SystemExit(f"Required command not found: {name}")


def run_checked(cmd: list[str], description: str) -> str:
    print(f"\n[{description}]")
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    print(proc.stdout.rstrip())
    if proc.returncode != 0:
        raise RuntimeError(f"{description} failed (exit {proc.returncode})")
    return proc.stdout


def ensure_csv(path: Path, header: list[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def append_csv(path: Path, row: list) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def make_session_log(path: Path, sessions: int, seed: int) -> None:
    rng = random.Random(seed)
    # This httperf build rejects more than 1000 session templates in the
    # input file. --wsesslog N still initiates the full N sessions; if N
    # exceeds the number of templates, httperf replays them round-robin.
    template_count = min(sessions, 1000)
    with path.open("w", encoding="utf-8") as f:
        for _ in range(template_count):
            principal = rng.randint(100_000, 2_000_000)
            annual_rate = round(rng.uniform(2.0, 20.0), 2)
            months = rng.choice([6, 12, 18, 24, 36, 48, 60])
            body = json.dumps({
                "principal": principal,
                "rate": annual_rate,
                "months": months
            }, separators=(",", ":"))
            # A blank line terminates each one-request httperf session.
            f.write(f"/api/emi method=POST contents='{body}'\n\n")


def parse_httperf(output: str) -> dict:
    def find_int(pattern: str):
        m = re.search(pattern, output, re.IGNORECASE)
        return int(m.group(1)) if m else None

    def find_float(pattern: str):
        m = re.search(pattern, output, re.IGNORECASE)
        return float(m.group(1)) if m else None

    requests = find_int(r"Total:\s+connections\s+\d+\s+requests\s+(\d+)")
    replies = find_int(r"Total:\s+connections\s+\d+\s+requests\s+\d+\s+replies\s+(\d+)")
    avg_response = find_float(r"Reply time\s*\[ms\]:\s*response\s+([\d.]+)")
    errors = find_int(r"Errors:\s+total\s+(\d+)")
    status_2xx = find_int(r"Reply status:.*?2xx=(\d+)")
    actual_rate = find_float(r"Request rate:\s*([\d.]+)\s+req/s")
    session_rate = find_float(r"Session rate\s*\[sess/s\]:\s*min\s+[\d.]+\s+avg\s+([\d.]+)")

    failed = None
    if requests is not None:
        error_count = errors or 0
        if status_2xx is not None:
            failed = max(error_count, requests - status_2xx)
        elif replies is not None:
            failed = max(error_count, requests - replies)
        else:
            failed = error_count

    return {
        "requests": requests,
        "replies": replies,
        "status_2xx": status_2xx,
        "avg_response_ms": avg_response,
        "httperf_errors": errors,
        "failed_requests": failed,
        "actual_request_rate": actual_rate,
        "average_session_rate": session_rate,
    }


def sample_pods(stop_event: threading.Event, run_id: str,
                replica_count: int, request_rate: int, errors: list[str]) -> None:
    next_sample = time.monotonic()
    while not stop_event.is_set():
        timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        proc = subprocess.run(
            ["kubectl", "top", "pods", "-n", "emi", "--no-headers"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=20
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 3:
                    append_csv(POD_CSV, [
                        timestamp, run_id, replica_count, request_rate,
                        fields[0], fields[1], fields[2]
                    ])
        else:
            errors.append(f"{timestamp}: kubectl top failed: {proc.stdout.strip()}")
        next_sample += 15
        delay = max(0, next_sample - time.monotonic())
        if stop_event.wait(delay):
            break


def parse_mpstat_json(path: Path, run_id: str, replica_count: int,
                      request_rate: int) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hosts = data["sysstat"]["hosts"]
        count = 0
        for host in hosts:
            host_date = host.get("date", "")
            for item in host.get("statistics", []):
                for cpu in item.get("cpu-load", []):
                    if cpu.get("cpu") == "all" and "idle" in cpu:
                        utilization = 100.0 - float(cpu["idle"])
                        timestamp = f"{host_date} {item.get('timestamp', '')}".strip()
                        append_csv(HOST_CSV, [
                            timestamp, run_id, replica_count, request_rate,
                            f"{utilization:.2f}"
                        ])
                        count += 1
        return count
    except Exception as exc:
        print(f"WARNING: Could not parse mpstat JSON {path}: {exc}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=DURATION,
                        help="seconds per run (assignment requires 60)")
    parser.add_argument("--rates", default="10,25,50,100,200")
    parser.add_argument("--replicas", default="1,2,3")
    args = parser.parse_args()

    if args.duration != 60:
        print("NOTE: Assignment specifies 60 seconds per fixed-replica experiment.")

    for cmd in ("kubectl", "httperf", "mpstat", "curl"):
        require_command(cmd)

    if not (ROOT / "k8s" / "07-emi-ingress.yaml").exists():
        raise SystemExit("Run from ~/projects/emi_milestone1 (k8s/07-emi-ingress.yaml not found).")

    # Ensure this is a fixed-replica test, not competing with an HPA.
    hpa = subprocess.run(["kubectl", "get", "hpa", "-n", "emi", "-o", "name"],
                         text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if hpa.returncode == 0 and hpa.stdout.strip():
        raise SystemExit("An HPA exists in namespace emi. Remove/disable it before fixed-replica tests.")

    curl = subprocess.run(["curl", "-fsS", "-o", "/dev/null", "http://emi.local/"])
    if curl.returncode != 0:
        raise SystemExit("Ingress preflight failed: http://emi.local/ is not reachable.")

    rates = [int(x) for x in args.rates.split(",")]
    replicas_list = [int(x) for x in args.replicas.split(",")]

    RESULTS.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)

    ensure_csv(SUMMARY_CSV, [
        "run_id", "replicas", "target_requests_per_sec", "duration_seconds",
        "scheduled_requests", "httperf_requests", "replies", "http_2xx",
        "average_response_ms", "httperf_errors", "failed_requests",
        "measured_request_rate", "measured_session_rate", "start_time",
        "end_time", "httperf_exit_code", "pod_metric_samples", "host_cpu_samples"
    ])
    ensure_csv(POD_CSV, [
        "timestamp", "run_id", "replicas", "target_requests_per_sec",
        "pod", "cpu", "memory"
    ])
    ensure_csv(HOST_CSV, [
        "timestamp", "run_id", "replicas", "target_requests_per_sec",
        "host_cpu_utilization_percent"
    ])

    # Rebuild completion state from valid measurements. The previous script
    # version incorrectly marked httperf startup failures as completed.
    valid_rows_by_id = {}
    if SUMMARY_CSV.exists():
        with SUMMARY_CSV.open(newline="", encoding="utf-8") as f:
            previous_rows = list(csv.DictReader(f))
        for row in previous_rows:
            try:
                run_id = row["run_id"]
                expected = int(row["scheduled_requests"])
                actual = int(row["httperf_requests"])
                exit_code = int(row["httperf_exit_code"])
                failed_count = int(row["failed_requests"])
                avg_response = float(row["average_response_ms"])
                is_valid = (
                    bool(run_id) and exit_code == 0
                    and actual == expected and failed_count >= 0
                    and avg_response >= 0
                )
            except (KeyError, TypeError, ValueError):
                is_valid = False
            if is_valid:
                valid_rows_by_id[run_id] = row

        fieldnames = [
            "run_id", "replicas", "target_requests_per_sec", "duration_seconds",
            "scheduled_requests", "httperf_requests", "replies", "http_2xx",
            "average_response_ms", "httperf_errors", "failed_requests",
            "measured_request_rate", "measured_session_rate", "start_time",
            "end_time", "httperf_exit_code", "pod_metric_samples", "host_cpu_samples"
        ]
        with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in valid_rows_by_id.values():
                writer.writerow(row)

        # Remove samples from invalid runs so the retried samples are clean.
        for metric_path in (POD_CSV, HOST_CSV):
            if metric_path.exists():
                with metric_path.open(newline="", encoding="utf-8") as f:
                    metric_rows = list(csv.DictReader(f))
                    metric_fields = list(metric_rows[0].keys()) if metric_rows else None
                if metric_fields:
                    with metric_path.open("w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=metric_fields)
                        writer.writeheader()
                        for row in metric_rows:
                            if row.get("run_id") in valid_rows_by_id:
                                writer.writerow(row)

    completed = set(valid_rows_by_id)
    COMPLETED_FILE.write_text(
        "".join(run_id + chr(10) for run_id in sorted(completed)),
        encoding="utf-8"
    )
    print(f"Validated and retained {len(completed)} previously completed runs; "
          f"{15 - len(completed)} runs remain or will be retried.")

    run_number = 0
    total_runs = len(replicas_list) * len(rates)
    print(f"\nFixed-replica experiment plan: {total_runs} runs, "
          f"{args.duration}s each, rates={rates}, replicas={replicas_list}.")
    print("One POST request is generated per httperf session; request inputs are randomised.")
    print("CSV and raw files will be saved under results/.")

    for replica_count in replicas_list:
        run_checked(
            ["kubectl", "scale", "deployment/emi-web",
             f"--replicas={replica_count}", "-n", "emi"],
            f"Scale web Deployment to {replica_count}"
        )
        run_checked(
            ["kubectl", "rollout", "status", "deployment/emi-web",
             "-n", "emi", "--timeout=180s"],
            f"Wait for {replica_count} web replicas to become Ready"
        )
        ready = subprocess.check_output(
            ["kubectl", "get", "pods", "-n", "emi", "-l", "app=emi-web",
             "--no-headers"], text=True
        )
        ready_count = sum(1 for line in ready.splitlines()
                          if len(line.split()) >= 2 and line.split()[1] == "1/1")
        if ready_count != replica_count:
            raise SystemExit(f"Expected {replica_count} Ready web pods, found {ready_count}.")

        for rate in rates:
            run_number += 1
            run_id = f"fixed_r{replica_count}_rate{rate}"
            if run_id in completed:
                print(f"\nSKIP {run_id}: already recorded complete.")
                continue

            sessions = rate * args.duration
            session_file = RAW / f"{run_id}.sessions"
            httperf_file = RAW / f"{run_id}_httperf.txt"
            mpstat_file = RAW / f"{run_id}_host_mpstat.json"
            monitor_error_file = RAW / f"{run_id}_monitor_errors.txt"

            make_session_log(session_file, sessions, seed=replica_count * 100000 + rate)
            httperf_cmd = [
                "httperf", "--hog",
                "--server=emi.local",
                "--port=80",
                "--server-name=emi.local",
                f"--wsesslog={sessions},0,{session_file}",
                f"--rate={rate}",
                "--timeout=15",
                "--add-header=Content-Type: application/json\\n",
            ]

            print("\n" + "=" * 68)
            print(f"RUN {run_number}/{total_runs}: {replica_count} replicas, "
                  f"{rate} POST requests/sec for {args.duration}s "
                  f"({sessions} one-request sessions)")
            print("=" * 68)

            start_dt = dt.datetime.now().astimezone()
            start_iso = start_dt.isoformat(timespec="seconds")
            monitor_stop = threading.Event()
            monitor_errors: list[str] = []
            pod_thread = threading.Thread(
                target=sample_pods,
                args=(monitor_stop, run_id, replica_count, rate, monitor_errors),
                daemon=True
            )

            with mpstat_file.open("w", encoding="utf-8") as mp_out:
                mp_proc = subprocess.Popen(
                    ["mpstat", "-o", "JSON", "1", str(args.duration)],
                    stdout=mp_out, stderr=subprocess.STDOUT,
                    env={**os.environ, "LC_ALL": "C"}
                )
                pod_thread.start()
                httperf_start = time.monotonic()
                httperf_proc = subprocess.run(
                    httperf_cmd, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )
                httperf_elapsed = time.monotonic() - httperf_start

                monitor_stop.set()
                pod_thread.join(timeout=25)

                try:
                    mp_proc.wait(timeout=args.duration + 20)
                except subprocess.TimeoutExpired:
                    mp_proc.terminate()
                    try:
                        mp_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        mp_proc.kill()
                        mp_proc.wait()

            end_dt = dt.datetime.now().astimezone()
            output = httperf_proc.stdout or ""
            httperf_file.write_text(
                "COMMAND: " + " ".join(httperf_cmd) + "\n\n" + output,
                encoding="utf-8"
            )
            monitor_error_file.write_text("\n".join(monitor_errors), encoding="utf-8")

            parsed = parse_httperf(output)
            pod_samples = sum(1 for line in POD_CSV.read_text(encoding="utf-8").splitlines()[1:]
                              if f",{run_id}," in line) if POD_CSV.exists() else 0
            host_samples = parse_mpstat_json(mpstat_file, run_id, replica_count, rate)

            append_csv(SUMMARY_CSV, [
                run_id, replica_count, rate, args.duration, sessions,
                parsed["requests"], parsed["replies"], parsed["status_2xx"],
                parsed["avg_response_ms"], parsed["httperf_errors"],
                parsed["failed_requests"], parsed["actual_request_rate"],
                parsed["average_session_rate"], start_iso,
                end_dt.isoformat(timespec="seconds"), httperf_proc.returncode,
                pod_samples, host_samples
            ])

            print(f"Run elapsed: {httperf_elapsed:.1f}s")
            print(f"httperf requests/replies: {parsed['requests']}/{parsed['replies']}")
            print(f"HTTP 2xx: {parsed['status_2xx']}; "
                  f"average response: {parsed['avg_response_ms']} ms")
            print(f"httperf errors: {parsed['httperf_errors']}; "
                  f"failed requests: {parsed['failed_requests']}")
            print(f"Per-pod metric rows captured: {pod_samples}")
            print(f"Host CPU samples captured: {host_samples}")
            if monitor_errors:
                print(f"Monitoring warnings: {len(monitor_errors)} "
                      f"(details: {monitor_error_file})")

            if httperf_proc.returncode != 0:
                print(f"WARNING: httperf exited with code {httperf_proc.returncode}. "
                      "Inspect its raw output before treating this run as valid.")
            if parsed["requests"] is None or parsed["avg_response_ms"] is None:
                print("WARNING: Could not parse one or more httperf summary fields. "
                      "Inspect the raw output.")

            run_is_valid = (
                httperf_proc.returncode == 0
                and parsed["requests"] == sessions
                and parsed["failed_requests"] is not None
                and parsed["avg_response_ms"] is not None
            )
            if run_is_valid:
                with COMPLETED_FILE.open("a", encoding="utf-8") as f:
                    f.write(run_id + chr(10))
                print("Run validated and marked complete.")
            else:
                print("Run NOT marked complete; it will be retried on the next execution.")

            print(f"Saved raw output: {httperf_file}")
            print(f"Saved summary row: {SUMMARY_CSV}")
            time.sleep(5)

    print("\n" + "=" * 68)
    print("FIXED-REPLICA EXPERIMENTS FINISHED")
    print(f"Summary CSV: {SUMMARY_CSV}")
    print(f"Per-pod metrics CSV: {POD_CSV}")
    print(f"Host CPU CSV: {HOST_CSV}")
    print(f"Raw outputs: {RAW}")
    print("The Deployment is left at the final requested replica count.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Completed runs are recorded; rerun this script to skip completed runs.")
        raise SystemExit(130)
