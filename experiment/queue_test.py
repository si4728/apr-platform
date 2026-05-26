import time
import threading
from experiment_runner import ExperimentRunner

class QueueTest(ExperimentRunner):
    def __init__(self):
        super().__init__(name="queue_stress")
        
    def run(self):
        self.connect()
        print(f"Starting Queue Stress Test: {self.experiment_id}")
        
        def publish_burst(thread_id, count):
            for i in range(count):
                payload = {
                    "sensor_id": f"queue_test_sensor",
                    "value": i,
                    "seq": i,
                    "thread_id": thread_id,
                    "policy": {"qos": 0, "compression": "none", "encryption": "none", "integrity": "none"}
                }
                self.publish_message("iot/sensor/queue_test", payload, qos=0)
                # No sleep, send as fast as possible to stress the queue
                
        threads = []
        for t in range(5):
            th = threading.Thread(target=publish_burst, args=(t, 200))
            threads.append(th)
            th.start()
            
        for th in threads:
            th.join()
            
        time.sleep(5) # wait for backlog to clear
        self.disconnect()
        print("Queue Stress Test Completed.")

if __name__ == "__main__":
    tester = QueueTest()
    tester.execute()
