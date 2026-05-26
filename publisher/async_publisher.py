import queue
import threading
import time

from network_emulation import apply_network_profile, normalize_network_profile

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


class AsyncPublisher:
    def __init__(
        self,
        mqtt_client,
        max_queue_size=1000,
        retry_count=1,
        retry_delay=0.05,
        network_profile=None,
    ):
        self.mqtt_client = mqtt_client
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.retry_count = int(retry_count)
        self.retry_delay = float(retry_delay)
        self.network_profile = normalize_network_profile(network_profile)
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.stats = {
            "queued": 0,
            "published": 0,
            "failed": 0,
            "dropped": 0,
            "emulated_dropped": 0,
            "emulated_delay_ms_total": 0.0,
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self, drain=True, timeout=5.0):
        if drain:
            deadline = time.time() + float(timeout)
            while not self.queue.empty() and time.time() < deadline:
                time.sleep(0.02)
        self.running = False
        if self.thread:
            self.thread.join(timeout=timeout)

    def publish(self, topic, payload, qos=0, retain=False, block=False, timeout=0.1):
        task = (topic, payload, int(qos), bool(retain))
        try:
            self.queue.put(task, block=block, timeout=timeout if block else 0)
            with self.lock:
                self.stats["queued"] += 1
            return True
        except queue.Full:
            with self.lock:
                self.stats["dropped"] += 1
            return False

    def get_stats(self):
        with self.lock:
            stats = dict(self.stats)
        stats["queue_depth"] = self.queue.qsize()
        stats["running"] = self.running
        stats["retry_count"] = self.retry_count
        stats["network_profile"] = dict(self.network_profile)
        return stats

    def _worker(self):
        while self.running or not self.queue.empty():
            try:
                topic, payload, qos, retain = self.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            result = self._publish_with_retry(topic, payload, qos, retain)
            with self.lock:
                if result == "published":
                    self.stats["published"] += 1
                elif result == "emulated_drop":
                    self.stats["emulated_dropped"] += 1
                else:
                    self.stats["failed"] += 1
            self.queue.task_done()

    def _publish_with_retry(self, topic, payload, qos, retain):
        emulation = apply_network_profile(self.network_profile)
        with self.lock:
            self.stats["emulated_delay_ms_total"] += emulation["delay_ms"]
        if emulation["dropped"]:
            return "emulated_drop"

        attempts = max(1, self.retry_count + 1)
        for attempt in range(attempts):
            try:
                info = self.mqtt_client.publish(topic, payload, qos=qos, retain=retain)
                rc = getattr(info, "rc", 0)
                success_rc = mqtt.MQTT_ERR_SUCCESS if mqtt else 0
                if rc == success_rc:
                    return "published"
            except Exception:
                pass
            if attempt < attempts - 1:
                time.sleep(self.retry_delay)
        return "failed"
