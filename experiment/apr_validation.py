import time
import requests
from experiment_runner import ExperimentRunner

class APRValidationTest(ExperimentRunner):
    def __init__(self):
        super().__init__(name="apr_validation")
        self.api_url = "http://127.0.0.1:5000/api/apr/recommend"
        
    def get_apr_recommendation(self, payload_size, latency, queue_depth, topic, schema_type):
        try:
            req_data = {
                "payload_size": payload_size,
                "network_latency_ms": latency,
                "queue_depth": queue_depth,
                "topic": topic,
                "schema_type": schema_type
            }
            res = requests.post(self.api_url, json=req_data)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f"API Error: {e}")
        # Default fallback
        return {"qos": 0, "compression": "none", "encryption": "none", "integrity": "none"}

    def run(self):
        self.connect()
        print(f"Starting APR Validation Test: {self.experiment_id}")
        
        test_cases = [
            {"name": "Normal Load", "size": 100, "latency": 10, "queue": 5, "topic": "iot/sensor/normal", "schema": "json"},
            {"name": "High Payload", "size": 2048, "latency": 10, "queue": 5, "topic": "iot/sensor/heavy", "schema": "json"},
            {"name": "High Latency", "size": 100, "latency": 150, "queue": 5, "topic": "iot/sensor/normal", "schema": "json"},
            {"name": "Critical Topic", "size": 100, "latency": 10, "queue": 5, "topic": "iot/sensor/critical", "schema": "sensitive"},
            {"name": "Queue Backlog", "size": 100, "latency": 10, "queue": 150, "topic": "iot/sensor/normal", "schema": "json"},
        ]
        
        for i, case in enumerate(test_cases):
            print(f"--- Testing APR Case {i}: {case['name']} ---")
            
            # Ask APR Engine
            rec_policy = self.get_apr_recommendation(case["size"], case["latency"], case["queue"], case["topic"], case["schema"])
            print(f"Received Policy: {rec_policy}")
            for j in range(3):
                payload = {
                    "sensor_id": f"apr_test_sensor",
                    "value": j,
                    "seq": j,
                    "unit": "unit",  # Add standard fields
                    "mode": "experiment",
                    "policy": rec_policy,
                    "padding": "A" * case["size"]
                }
                self.publish_message(case["topic"], payload, qos=rec_policy.get("qos", 0), policy=rec_policy)
                time.sleep(0.5)
                
        time.sleep(2)
        self.disconnect()
        print("APR Validation Test Completed.")

if __name__ == "__main__":
    tester = APRValidationTest()
    tester.execute()
