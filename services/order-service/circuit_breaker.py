import time
import threading

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=15):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "closed"
        self.opened_at = None
        self.lock = threading.Lock()

    def record_success(self):
        with self.lock:
            self.failure_count = 0
            self.state = "closed"

    def record_failure(self):
        with self.lock:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.opened_at = time.time()

    def allow_request(self):
        with self.lock:
            if self.state == "open":
                if time.time() - self.opened_at >= self.recovery_timeout:
                    self.state = "half-open"
                    return True
                return False
            return True

    def get_state(self):
        with self.lock:
            return self.state
