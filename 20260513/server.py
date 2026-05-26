from flask import Flask, render_template, jsonify, request
import sqlite3
import json
import paho.mqtt.client as mqtt

app = Flask(__name__)

DB_NAME = "iot_data.db"
CONFIG_FILE = "config.json"


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT,
            sensor_type TEXT,
            value REAL,
            unit TEXT,
            timestamp TEXT
        )
    """)

    cur.execute("PRAGMA table_info(sensor_data)")
    columns = [row[1] for row in cur.fetchall()]

    if "topic" not in columns:
        cur.execute("ALTER TABLE sensor_data ADD COLUMN topic TEXT")

    if "mode" not in columns:
        cur.execute("ALTER TABLE sensor_data ADD COLUMN mode TEXT")

    conn.commit()
    conn.close()


def insert_sensor_data(data):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sensor_data
        (sensor_id, sensor_type, value, unit, topic, mode, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("sensor_id"),
        data.get("sensor_type"),
        data.get("value"),
        data.get("unit"),
        data.get("topic"),
        data.get("mode"),
        data.get("timestamp")
    ))

    conn.commit()
    conn.close()


def on_connect(client, userdata, flags, rc):
    print("MQTT connected:", rc)
    client.subscribe("iot/sensor/#")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        insert_sensor_data(data)
        print("Received:", data)
    except Exception as e:
        print("MQTT message error:", e)


def start_mqtt():
    config = load_config()
    broker = config["mqtt"]["broker"]
    port = config["mqtt"]["port"]

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port, 60)
    client.loop_start()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/stats")
def api_stats():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sensor_id,
            sensor_type,
            COUNT(*),
            ROUND(AVG(value), 2),
            ROUND(MIN(value), 2),
            ROUND(MAX(value), 2)
        FROM sensor_data
        GROUP BY sensor_id, sensor_type
    """)

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "sensor_id": r[0],
            "sensor_type": r[1],
            "count": r[2],
            "avg": r[3],
            "min": r[4],
            "max": r[5]
        }
        for r in rows
    ])


@app.route("/api/chart/<sensor_id>")
def api_chart(sensor_id):
    limit = request.args.get("limit", default=200, type=int)

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT timestamp, value
        FROM sensor_data
        WHERE sensor_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (sensor_id, limit))

    rows = cur.fetchall()
    conn.close()

    rows.reverse()

    return jsonify({
        "labels": [r[0][11:19] if r[0] else "" for r in rows],
        "values": [r[1] for r in rows]
    })


@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_config())


@app.route("/api/sensors", methods=["GET"])
def api_get_sensors():
    config = load_config()
    return jsonify(config.get("sensors", []))


@app.route("/api/sensors", methods=["POST"])
def api_add_sensor():
    data = request.json
    config = load_config()

    sensors = config.get("sensors", [])

    for s in sensors:
        if s["id"] == data["id"]:
            return jsonify({"error": "sensor id already exists"}), 400

    if not data.get("topic"):
        topic_prefix = config["mqtt"]["topic_prefix"]
        data["topic"] = f"{topic_prefix}/{data['id']}"

    sensors.append(data)
    config["sensors"] = sensors
    save_config(config)

    return jsonify({"message": "sensor added"})


@app.route("/api/sensors/<sensor_id>", methods=["PUT"])
def api_update_sensor(sensor_id):
    data = request.json
    config = load_config()

    sensors = config.get("sensors", [])

    for i, s in enumerate(sensors):
        if s["id"] == sensor_id:
            sensors[i] = data
            config["sensors"] = sensors
            save_config(config)
            return jsonify({"message": "sensor updated"})

    return jsonify({"error": "sensor not found"}), 404


@app.route("/api/sensors/<sensor_id>", methods=["DELETE"])
def api_delete_sensor(sensor_id):
    config = load_config()

    sensors = config.get("sensors", [])
    sensors = [s for s in sensors if s["id"] != sensor_id]

    config["sensors"] = sensors
    save_config(config)

    return jsonify({"message": "sensor deleted"})


if __name__ == "__main__":
    init_db()
    start_mqtt()
    app.run(host="0.0.0.0", port=5000, debug=True)