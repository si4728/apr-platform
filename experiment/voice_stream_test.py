import os
import sys
import time
import json
import sqlite3
import subprocess
import argparse
import uuid
from datetime import datetime, timezone

# Add parent path to allow easy reference if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def run_voice_experiment(duration_s, fps, prebuffer_ms, drop_on, qos, payload_bytes=160):
    experiment_id = f"EXP_VOICE_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    scenario = f"voice_fps{fps}_pre{prebuffer_ms}_drop{1 if drop_on else 0}_qos{qos}"
    
    # Path setup
    tool_path = r"c:\access\schedule\study\voice_over_mqtt\code\mqtt_voice_experiment_full_stable.py"
    if not os.path.exists(tool_path):
        print(f"Error: G.711 Stable tool not found at {tool_path}")
        return None
        
    results_dir = "experiment_results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
        
    csv_path = os.path.abspath(os.path.join(results_dir, f"{experiment_id}.csv"))
    summary_path = csv_path.replace(".csv", ".summary.json")
    
    # Read MQTT broker config
    broker = "218.146.225.166"
    port = 1883
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
            if "mqtt" in config:
                broker = config["mqtt"].get("broker", broker)
                port = config["mqtt"].get("port", port)
    except Exception:
        pass
        
    topic = f"vom/test/realtime_{uuid.uuid4().hex[:8]}"
    
    print(f"[{experiment_id}] Spawning G.711 Subscriber on topic '{topic}'...")
    sub_cmd = [
        sys.executable,
        tool_path,
        "subscribe",
        "--host", broker,
        "--port", str(port),
        "--topic", topic,
        "--qos", str(qos),
        "--duration-s", str(duration_s),
        "--fps", str(fps),
        "--prebuffer-ms", str(prebuffer_ms),
        "--csv", csv_path,
        "--scenario", scenario
    ]
    if drop_on:
        sub_cmd.append("--drop-on")
        
    sub_proc = subprocess.Popen(sub_cmd)
    
    # Warmup time for subscriber to connect
    time.sleep(2.0)
    
    # Max frames is duration * fps
    max_frames = int(duration_s * fps)
    print(f"[{experiment_id}] Running G.711 Publisher...")
    pub_cmd = [
        sys.executable,
        tool_path,
        "publish",
        "--host", broker,
        "--port", str(port),
        "--topic", topic,
        "--qos", str(qos),
        "--fps", str(fps),
        "--max-frames", str(max_frames),
        "--payload-bytes", str(payload_bytes)
    ]
    
    pub_res = subprocess.run(pub_cmd)
    
    # Wait for subscriber to cleanly dump CSV and JSON summary
    print(f"[{experiment_id}] Waiting for Subscriber to finalize...")
    try:
        sub_proc.wait(timeout=duration_s + 10)
    except subprocess.TimeoutExpired:
        sub_proc.terminate()
        sub_proc.wait()
        
    # Read summary JSON
    if not os.path.exists(summary_path):
        print(f"Error: Summary JSON not generated at {summary_path}")
        return None
        
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception as e:
        print(f"Failed to read summary JSON: {e}")
        return None
        
    # Insert results into SQLite
    db_path = "iot_data.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Ensure table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_experiment_results (
            experiment_id TEXT PRIMARY KEY,
            scenario TEXT,
            topic TEXT,
            qos INTEGER,
            fps REAL,
            prebuffer_ms INTEGER,
            max_queue_ms INTEGER,
            drop_on INTEGER,
            duration_s INTEGER,
            received_frames INTEGER,
            played_ticks INTEGER,
            played_frames INTEGER,
            gap_inserted INTEGER,
            gap_ratio_pct REAL,
            latency_avg_ms REAL,
            latency_p95_ms REAL,
            latency_p99_ms REAL,
            latency_max_ms REAL,
            jitter_ms REAL,
            created_at TEXT
        )
    """)
    
    # Insert record
    cur.execute("""
        INSERT INTO voice_experiment_results (
            experiment_id, scenario, topic, qos, fps, prebuffer_ms, max_queue_ms, drop_on, duration_s,
            received_frames, played_ticks, played_frames, gap_inserted, gap_ratio_pct,
            latency_avg_ms, latency_p95_ms, latency_p99_ms, latency_max_ms, jitter_ms, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        experiment_id,
        scenario,
        topic,
        qos,
        fps,
        prebuffer_ms,
        summary.get("max_queue_ms", 2000),
        1 if drop_on else 0,
        duration_s,
        summary.get("received_frames", 0),
        summary.get("played_ticks", 0),
        summary.get("played_frames", 0),
        summary.get("gap_inserted", 0),
        summary.get("gap_ratio_pct", 0.0),
        summary.get("latency_avg_ms", 0.0),
        summary.get("latency_p95_ms", 0.0),
        summary.get("latency_p99_ms", 0.0),
        summary.get("latency_max_ms", 0.0),
        summary.get("network_jitter_std_ms", 0.0),
        now_iso()
    ))
    conn.commit()
    conn.close()
    
    print(f"[{experiment_id}] Voice Streaming experiment completed and saved successfully!")
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Stream Experiment Runner")
    parser.add_argument("--duration", type=int, default=15, help="Test duration in seconds")
    parser.add_argument("--fps", type=float, default=50.0, help="Frames per second")
    parser.add_argument("--prebuffer", type=int, default=300, help="Prebuffer in milliseconds")
    parser.add_argument("--drop-on", action="store_true", default=False, help="Enable queue drops")
    parser.add_argument("--qos", type=int, default=0, help="MQTT QoS")
    parser.add_argument("--payload-bytes", type=int, default=160, help="Frame payload size")
    
    args = parser.parse_args()
    res = run_voice_experiment(
        duration_s=args.duration,
        fps=args.fps,
        prebuffer_ms=args.prebuffer,
        drop_on=args.drop_on,
        qos=args.qos,
        payload_bytes=args.payload_bytes
    )
    if res:
        print(json.dumps(res, indent=2))
