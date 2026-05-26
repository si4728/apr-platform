import time
from experiment_runner import ExperimentRunner

class SchemaVariationTest(ExperimentRunner):
    def __init__(self):
        super().__init__(name="schema_variation")
        
    def run(self):
        self.connect()
        print(f"Starting Schema Variation Test: {self.experiment_id}")
        
        schemas = [
            {"sensor_id": "schema_test", "temperature": 25.5}, # valid simple schema
            {"sensor_id": "schema_test", "temp": 25.5, "unit": "C"}, # different key schema
            {"sensor_id": "schema_test", "measurements": {"temp": 25.5, "humi": 60}}, # nested schema
            {"node": "edge_1", "cpu": 50, "memory": 2048} # completely different schema
        ]
        
        for i, payload in enumerate(schemas):
            print(f"--- Testing Schema {i} ---")
            for j in range(5):
                payload["seq"] = j
                payload["policy"] = {"qos": 0, "compression": "none", "encryption": "none", "integrity": "none"}
                self.publish_message("iot/sensor/schema_test", payload, qos=0)
                time.sleep(0.5)
                
        time.sleep(2)
        self.disconnect()
        print("Schema Variation Test Completed.")

if __name__ == "__main__":
    tester = SchemaVariationTest()
    tester.execute()
