HYPOTHESES = {
    "payment-latency": {
        "experiment_file": "payment-latency.yaml",
        "experiment_kind": "NetworkChaos",
        "service": "payment-service",
        "description": "Payment Service under 3s network latency",
        "expected_behavior": "Order Service retries absorb the delay or circuit-breaks; no cascading failure to the user",
        "remedy": "Tune retry budget and circuit-breaker thresholds; add a Payment replica if sustained latency persists.",
        "prometheus_evidence": (
            "histogram_quantile(0.99, sum(rate(order_service_request_latency_seconds_bucket[1m])) by (le)); "
            "sum(rate(order_service_requests_total{status=~\"5..\"}[1m])) / sum(rate(order_service_requests_total[1m]))"
        ),
        "slo_thresholds": {
            "error_rate_max": 0.20,
            "p99_latency_max_seconds": 5.0,
            "circuit_breaker_must_open": False
        }
    },
    "payment-severe-latency": {
        "experiment_file": "payment-severe-latency.yaml",
        "experiment_kind": "NetworkChaos",
        "service": "payment-service",
        "description": "Payment Service under 8s network latency, exceeding retry capacity",
        "expected_behavior": "Retries cannot absorb this; circuit breaker must open to protect the system",
        "remedy": "Verify circuit-breaker open threshold (failure count / window); ensure per-pod breaker metrics are aggregated; consider increasing Payment replicas.",
        "prometheus_evidence": (
            "max(order_service_circuit_breaker_state) without (instance, pod); "
            "histogram_quantile(0.99, sum(rate(order_service_request_latency_seconds_bucket[1m])) by (le))"
        ),
        "slo_thresholds": {
            "error_rate_max": 0.20,
            "p99_latency_max_seconds": 5.0,
            "circuit_breaker_must_open": True
        }
    },
    "kill-payment-pod": {
        "experiment_file": "kill-payment-pod.yaml",
        "experiment_kind": "PodChaos",
        "service": "payment-service",
        "description": "Single Payment Service pod killed",
        "expected_behavior": "Traffic shifts to surviving replica; no order failures",
        "remedy": "Ensure at least 2 Payment replicas are scheduled; add PodDisruptionBudget; verify readiness probe timing.",
        "prometheus_evidence": (
            "sum(rate(order_service_requests_total{status=~\"5..\"}[1m])) / sum(rate(order_service_requests_total[1m])); "
            "kube_pod_container_status_restarts_total{container=\"payment-service\"}"
        ),
        "slo_thresholds": {
            "error_rate_max": 0.05,
            "p99_latency_max_seconds": 2.0,
            "circuit_breaker_must_open": False
        }
    },
    "payment-cpu-stress": {
        "experiment_file": "payment-cpu-stress.yaml",
        "experiment_kind": "StressChaos",
        "service": "payment-service",
        "description": "Payment Service under CPU stress (2 workers, 100% load)",
        "expected_behavior": "Increased latency but continued availability",
        "remedy": "Add CPU requests/limits; horizontal-scale Payment Service; profile hot code paths.",
        "prometheus_evidence": (
            "rate(container_cpu_usage_seconds_total{pod=~\"payment-service.*\"}[1m]); "
            "histogram_quantile(0.99, sum(rate(order_service_request_latency_seconds_bucket[1m])) by (le))"
        ),
        "slo_thresholds": {
            "error_rate_max": 0.10,
            "p99_latency_max_seconds": 3.0,
            "circuit_breaker_must_open": False
        }
    }
}
