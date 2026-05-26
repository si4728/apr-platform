import time
from collections import deque
import threading

class QueueMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.topic_counts = {}  # topic -> {timestamp_sec: count}
        self.processing_delays = deque(maxlen=200) # stores last 200 processing times (ms)
        self.current_backlog = 0
        self.dropped_messages = 0
        self.total_processed = 0

    def record_receive(self, topic):
        with self.lock:
            now = int(time.time())
            if topic not in self.topic_counts:
                self.topic_counts[topic] = {}
            self.topic_counts[topic][now] = self.topic_counts[topic].get(now, 0) + 1
            self.current_backlog += 1

    def record_processed(self, delay_ms):
        with self.lock:
            self.processing_delays.append(delay_ms)
            if self.current_backlog > 0:
                self.current_backlog -= 1
            self.total_processed += 1

    def record_drop(self):
        with self.lock:
            self.dropped_messages += 1
            if self.current_backlog > 0:
                self.current_backlog -= 1

    def get_topic_rates(self):
        with self.lock:
            now = int(time.time())
            rates = {}
            for topic, counts in list(self.topic_counts.items()):
                # clean up old seconds
                for t in list(counts.keys()):
                    if now - t > 60: # keep last 60 seconds
                        del counts[t]
                
                # compute rate (msgs/sec over last 5 seconds)
                recent_total = sum(count for t, count in counts.items() if now - t <= 5)
                rates[topic] = round(recent_total / 5.0, 2)
            return sorted([{"topic": k, "rate": v} for k, v in rates.items()], key=lambda x: x["rate"], reverse=True)

    def get_queue_stats(self):
        with self.lock:
            avg_delay = sum(self.processing_delays) / len(self.processing_delays) if self.processing_delays else 0
            # Load estimation: if avg_delay > 100ms and backlog is growing, load is high
            load_factor = min(1.0, avg_delay / 150.0) # normalize up to 150ms processing
            
            return {
                "backlog": self.current_backlog,
                "dropped": self.dropped_messages,
                "total_processed": self.total_processed,
                "avg_processing_delay_ms": round(avg_delay, 2),
                "subscriber_load_percent": round(load_factor * 100, 2)
            }

queue_monitor = QueueMonitor()
