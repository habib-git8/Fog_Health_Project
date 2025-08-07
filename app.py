import streamlit as st
import pandas as pd
import threading
import time
import random
import csv
import boto3
from queue import Queue

stop_signal = object()
CLOUD_FILE = "cloud_storage.csv"
log_messages = []

# AWS S3 Configuration
S3_BUCKET_NAME = "fog-health-bucket" 

# Upload to S3 function
def upload_to_s3(local_file, bucket_name, object_name=None):
    s3 = boto3.client("s3")
    if object_name is None:
        object_name = local_file
    try:
        s3.upload_file(local_file, bucket_name, object_name)
        print(f"✅ Uploaded '{local_file}' to S3 bucket '{bucket_name}' as '{object_name}'")
    except Exception as e:
        print(f"❌ Failed to upload to S3: {e}")

# IoT Sensor Data Generator
def generate_sensor_data(sensor_id):
    return {
        "sensor_id": sensor_id,
        "heart_rate": random.randint(60, 140),
        "temperature": round(random.uniform(36.0, 39.0), 1),
        "pulse_rate": random.randint(60, 120),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

# Fog Node Processing
def fog_node(node_id, task_queue, cloud_queue, log):
    while True:
        data = task_queue.get()
        if data is stop_signal:
            task_queue.task_done()
            break
        time.sleep(1)
        alert = data["heart_rate"] > 100 or data["temperature"] > 37.5
        data["alert"] = "YES" if alert else "NO"
        data["fog_node"] = node_id
        log.append(f"🌀 Fog Node {node_id} processing from Sensor {data['sensor_id']}")
        if alert:
            cloud_queue.put(data)
        task_queue.task_done()

# Cloud Storage Writer
def cloud_storage_consumer(cloud_queue, log):
    with open(CLOUD_FILE, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "sensor_id", "heart_rate", "temperature", "pulse_rate", "alert", "fog_node"])
        writer.writeheader()
        while True:
            data = cloud_queue.get()
            if data is stop_signal:
                cloud_queue.task_done()
                break
            writer.writerow(data)
            log.append(f"☁️  Data stored in cloud from Sensor {data['sensor_id']}")
            cloud_queue.task_done()

# Simulation logic with log tracking
def run_simulation(num_sensors=10, duration_sec=30):
    fog1_queue = Queue()
    fog2_queue = Queue()
    cloud_queue = Queue()
    log = []

    fog1_thread = threading.Thread(target=fog_node, args=("F1", fog1_queue, cloud_queue, log))
    fog2_thread = threading.Thread(target=fog_node, args=("F2", fog2_queue, cloud_queue, log))
    cloud_thread = threading.Thread(target=cloud_storage_consumer, args=(cloud_queue, log))

    fog1_thread.start()
    fog2_thread.start()
    cloud_thread.start()

    start_time = time.time()
    count = 0
    while time.time() - start_time < duration_sec:
        sensor_id = count % num_sensors
        data = generate_sensor_data(sensor_id)
        if count % 2 == 0:
            fog1_queue.put(data)
        else:
            fog2_queue.put(data)
        count += 1
        time.sleep(0.5)

    fog1_queue.put(stop_signal)
    fog2_queue.put(stop_signal)
    cloud_queue.put(stop_signal)

    fog1_thread.join()
    fog2_thread.join()
    cloud_thread.join()

    # Upload to S3
    upload_to_s3(CLOUD_FILE, S3_BUCKET_NAME)

    return log

# Streamlit UI
st.set_page_config(layout="wide")
st.title("💻 Fog-Based Health Monitoring Dashboard")

st.markdown("This dashboard simulates IoT sensor data, processes it at Fog nodes, and stores alerts in the Cloud and S3.")

log_area = st.empty()

if st.button("▶️ Start Simulation"):
    with st.spinner("Running simulation for 30 seconds..."):
        logs = run_simulation()
        for line in logs:
            time.sleep(0.1)
            log_area.markdown(f"```\n{line}\n```")

st.markdown("---")
st.subheader("📦 Cloud Storage Data (Alerts Only)")

try:
    df = pd.read_csv(CLOUD_FILE)
    st.dataframe(df, use_container_width=True)

    st.subheader("📊 Heart Rate Distribution")
    st.bar_chart(df["heart_rate"])

    st.subheader("🌡️ Temperature Distribution")
    st.bar_chart(df["temperature"])

    st.subheader("🧠 Fog Node Usage")
    st.bar_chart(df["fog_node"].value_counts())

except Exception as e:
    st.warning("No data available. Run the simulation first.")
