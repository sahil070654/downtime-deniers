import sys
import time
import json
import argparse
import subprocess
import threading
import concurrent.futures
import requests as http_requests
from datetime import datetime, timezone
from pathlib import Path
from prometheus_api_client import PrometheusConnect
from hypotheses import HYPOTHESES
import jira_client as jira

PROMETHEUS_URL = "http://localhost:30090"
ORDER_SERVICE_URL = "http://localhost:30002/api/orders"
STATE_FILE = Path(__file__).parent / "state.json"


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"open_ticket": None, "open_experiment": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def apply_experiment(yaml_file):
    print("[ChaosDrill] Deleting any existing experiment first...")
    subprocess.run(["kubectl", "delete", "-f", yaml_file, "--ignore-not-found"],
                   capture_output=True, text=True)
    time.sleep(2)
    print(f"[ChaosDrill] Applying experiment: {yaml_file}")
    result = subprocess.run(["kubectl", "apply", "-f", yaml_file],
                            capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to apply experiment: {result.stderr}")


def generate_traffic(stop_event, interval=1, concurrency=4):
    def send_one():
        try:
            http_requests.post(
                ORDER_SERVICE_URL,
                json={"userId": 1, "itemName": "ChaosDrillTest",
                      "quantity": 1, "amount": 50.00},
                timeout=12,
            )
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        while not stop_event.is_set():
            for _ in range(concurrency):
                executor.submit(send_one)
            time.sleep(interval)


def query_metric(prom, query):
    try:
        result = prom.custom_query(query=query)
        if result and len(result) > 0:
            val = float(result[0]["value"][1])
            return 0.0 if val != val else val
        return 0.0
    except Exception as e:
        print(f"[ChaosDrill] Warning: query failed ({query}): {e}")
        return 0.0


def poll_metrics(prom, duration_seconds, interval_seconds=5):
    readings = []
    elapsed = 0
    while elapsed < duration_seconds:
        error_rate = query_metric(
            prom,
            'sum(rate(order_service_requests_total{status=~"5.."}[1m])) / sum(rate(order_service_requests_total[1m])) or vector(0)')
        p99_latency = query_metric(
            prom,
            'histogram_quantile(0.99, sum(rate(order_service_request_latency_seconds_bucket[1m])) by (le))')
        breaker_state = query_metric(
            prom,
            'max(order_service_circuit_breaker_state) without (instance, pod)')

        reading = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_rate": error_rate,
            "p99_latency_seconds": p99_latency,
            "circuit_breaker_state": breaker_state,
        }
        readings.append(reading)
        print(f"[ChaosDrill] t+{elapsed}s | error_rate={error_rate:.3f} | "
              f"p99={p99_latency:.2f}s | breaker={breaker_state}")
        time.sleep(interval_seconds)
        elapsed += interval_seconds
    return readings


def judge(readings, thresholds):
    max_error_rate = max(r["error_rate"] for r in readings)
    max_p99 = max(r["p99_latency_seconds"] for r in readings)
    breaker_opened = any(r["circuit_breaker_state"] >= 1 for r in readings)

    violations = []
    if max_error_rate > thresholds["error_rate_max"]:
        violations.append(f"Error rate {max_error_rate:.2%} exceeded threshold {thresholds['error_rate_max']:.2%}")
    if max_p99 > thresholds["p99_latency_max_seconds"]:
        violations.append(f"P99 latency {max_p99:.2f}s exceeded threshold {thresholds['p99_latency_max_seconds']}s")
    if thresholds["circuit_breaker_must_open"] and not breaker_opened:
        violations.append("Circuit breaker was expected to open but never did")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "max_error_rate": max_error_rate,
        "max_p99_latency_seconds": max_p99,
        "circuit_breaker_opened": breaker_opened,
    }


def run_experiment(name, force=False):
    if name not in HYPOTHESES:
        raise ValueError(f"Unknown experiment: {name}. Available: {list(HYPOTHESES.keys())}")

    state = load_state()

    if not force:
        blocker = state.get("open_ticket") or jira.find_open_blocker()

        if blocker:
            owning_exp = state.get("open_experiment")

            if not owning_exp:
                for candidate in HYPOTHESES.keys():
                    if jira.find_open_issue_for_experiment(candidate) == blocker:
                        owning_exp = candidate
                        state["open_experiment"] = candidate
                        state["open_ticket"] = blocker
                        save_state(state)
                        break

            if owning_exp == name:
                print(f"\n[ChaosDrill] Re-verifying '{name}' against open ticket {blocker}.")
                print("[ChaosDrill] If it PASSES now, the ticket will auto-resolve and unblock.")
            else:
                print(f"\n[ChaosDrill] BLOCKED: open Jira ticket {blocker} must be resolved first.")
                if owning_exp:
                    print(f"[ChaosDrill] Re-run the owning experiment to close the loop: {owning_exp}")
                else:
                    print("[ChaosDrill] Fix + redeploy, then re-run the experiment that opened the ticket.")
                print("[ChaosDrill] Use --force to override (not recommended).")
                if state.get("open_ticket") != blocker:
                    state["open_ticket"] = blocker
                    save_state(state)
                sys.exit(2)

    hyp = HYPOTHESES[name]
    print(f"\n[ChaosDrill] === Running experiment: {name} ===")
    print(f"[ChaosDrill] Hypothesis: {hyp['expected_behavior']}")

    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
    apply_experiment(hyp["experiment_file"])

    stop_event = threading.Event()
    traffic_thread = threading.Thread(target=generate_traffic, args=(stop_event,))
    traffic_thread.start()

    print("[ChaosDrill] Polling metrics for 70 seconds (concurrent traffic in background)...")
    readings = poll_metrics(prom, duration_seconds=70, interval_seconds=5)

    stop_event.set()
    traffic_thread.join(timeout=15)

    verdict = judge(readings, hyp["slo_thresholds"])

    report = {
        "experiment": name,
        "kind": hyp["experiment_kind"],
        "service": hyp.get("service", "unknown"),
        "description": hyp["description"],
        "hypothesis": hyp["expected_behavior"],
        "remedy": hyp.get("remedy", "N/A"),
        "prometheus_evidence": hyp.get("prometheus_evidence", ""),
        "thresholds": hyp["slo_thresholds"],
        "started_at": readings[0]["timestamp"],
        "finished_at": readings[-1]["timestamp"],
        "verdict": verdict,
        "raw_readings": readings,
    }

    report_file = f"report_{name}_{int(time.time())}.json"

    print(f"\n[ChaosDrill] === RESULT: {'PASS' if verdict['passed'] else 'FAIL'} ===")

    if not verdict["passed"]:
        for v in verdict["violations"]:
            print(f"[ChaosDrill]   - VIOLATION: {v}")

        existing = state.get("open_ticket") or jira.find_open_issue_for_experiment(name)
        if existing:
            jira.add_comment(
                existing,
                f"ChaosDrill re-ran '{name}' and it FAILED again.\n"
                f"Violations: {verdict['violations']}\n"
                f"Max error rate: {verdict['max_error_rate']:.2%}\n"
                f"Max P99: {verdict['max_p99_latency_seconds']:.2f}s"
            )
            ticket_key = existing
            print(f"[ChaosDrill] Reused existing Jira ticket: {ticket_key}")
        else:
            ticket_key = jira.create_incident_ticket(report)

        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[ChaosDrill] Report saved: {report_file}")

        if ticket_key:
            jira.attach_file(ticket_key, report_file)
            report["jira_ticket"] = ticket_key
            state["open_ticket"] = ticket_key
            state["open_experiment"] = name
            save_state(state)
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)

        print(f"[ChaosDrill] Next experiments BLOCKED until {ticket_key} is resolved.")
        sys.exit(1)

    print(f"[ChaosDrill] SLO satisfied for {name}")

    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[ChaosDrill] Report saved: {report_file}")

    open_ticket = state.get("open_ticket") or jira.find_open_issue_for_experiment(name)
    if open_ticket:
        jira.add_comment(
            open_ticket,
            f"ChaosDrill re-verification PASSED for '{name}'.\n"
            f"Max error rate: {verdict['max_error_rate']:.2%}\n"
            f"Max P99: {verdict['max_p99_latency_seconds']:.2f}s\n"
            f"Circuit breaker opened: {verdict['circuit_breaker_opened']}\n"
            f"Report file: {report_file}"
        )
        jira.attach_file(open_ticket, report_file)
        if jira.resolve_ticket(open_ticket):
            print(f"[ChaosDrill] Jira {open_ticket} resolved. Next experiment UNBLOCKED.")
            state["open_ticket"] = None
            state["open_experiment"] = None
            save_state(state)
            report["jira_ticket"] = open_ticket
            report["resolved"] = True
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
        else:
            print(f"[ChaosDrill] Auto-resolve failed for {open_ticket}. Resolve manually in Jira.")
    else:
        print("[ChaosDrill] No matching open Jira ticket. Nothing to resolve.")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("experiment", help="Experiment name from hypotheses.py")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the Jira blocker check (testing only)")
    args = parser.parse_args()
    run_experiment(args.experiment, force=args.force)
