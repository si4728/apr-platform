import time
from experiment_runner import ExperimentRunner

class QoSTest(ExperimentRunner):
    def __init__(self):
        super().__init__(name="qos_test")
        
    def run(self):
        self.connect()
        print(f"Starting QoS Test: {self.experiment_id}")
        
        for qos in [0, 1, 2]:
            print(f"--- Testing QoS {qos} ---")
            for i in range(10):
                payload = {
                    "sensor_id": f"qos_test_sensor",
                    "value": i,
                    "seq": i,
                    "policy": {"qos": qos, "compression": "none", "encryption": "none", "integrity": "none"}
                }
                self.publish_message("iot/sensor/qos_test", payload, qos=qos)
                time.sleep(0.5)
                
        time.sleep(2) # wait for all to be delivered
        self.disconnect()
        print("QoS Test Completed.")

if __name__ == "__main__":
    tester = QoSTest()
    tester.execute()
