from collections import defaultdict, deque
from threading import Lock
from time import time


class MetricsStore:
    def __init__(self):
        self._lock = Lock()
        self._started_at = time()
        self._received = 0
        self._forwarded = 0
        self._failed = 0
        self._last_error = None
        self._topic_counts = defaultdict(int)
        self._policies = {}
        self._latencies = deque(maxlen=500)
        self._queue_depth = 0

    def record_received(self, topic: str):
        with self._lock:
            self._received += 1
            self._topic_counts[topic] += 1

    def record_forwarded(self, topic: str, policy: dict, latency_ms: float):
        with self._lock:
            self._forwarded += 1
            self._policies[topic] = {"policy": policy, "updated_at": time()}
            self._latencies.append(float(latency_ms))

    def record_failed(self, error: str):
        with self._lock:
            self._failed += 1
            self._last_error = error

    def set_queue_depth(self, depth: int):
        with self._lock:
            self._queue_depth = depth

    def snapshot(self) -> dict:
        with self._lock:
            latencies = list(self._latencies)
            avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
            return {
                "uptime_seconds": round(time() - self._started_at, 3),
                "received": self._received,
                "forwarded": self._forwarded,
                "failed": self._failed,
                "queue_depth": self._queue_depth,
                "avg_processing_latency_ms": round(avg_latency, 3),
                "topic_counts": dict(self._topic_counts),
                "last_error": self._last_error,
            }

    def policy_snapshot(self) -> dict:
        with self._lock:
            return dict(self._policies)
