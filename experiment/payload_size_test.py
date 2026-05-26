import time
from experiment_runner import ExperimentRunner

class PayloadSizeTest(ExperimentRunner):
    def __init__(self):
        super().__init__(name="payload_size")
        
    def run(self):
        self.connect()
        print(f"Starting Payload Size Test: {self.experiment_id}")
        
        sizes = [100, 500, 1024, 4096, 10240]
        for size in sizes:
            print(f"--- Testing Size {size} bytes ---")
            for i in range(5):
                # Generate dummy padding
                padding = "A" * size
                payload = {
                    "sensor_id": f"size_test",
                    "padding": padding,
                    "seq": i,
                    "policy": {"qos": 0, "compression": "none", "encryption": "none", "integrity": "none"}
                }
                self.publish_message("iot/sensor/size_test", payload, qos=0)
                time.sleep(0.5)
                
        time.sleep(2)
        self.disconnect()
        print("Payload Size Test Completed.")

if __name__ == "__main__":
    tester = PayloadSizeTest()
    tester.execute()
