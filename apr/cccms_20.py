import hashlib
import time
import zlib
import gzip
import bz2
import lzma
import lz4.frame
import snappy
import json
import threading
import os
import paho.mqtt.client as mqtt
import matplotlib.pyplot as plt
from collections import defaultdict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
from speck import SpeckCipher
import ascon
import base64
import pping
import configparser
from cccm_sinario import combinations_with_id, get_configuration_by_id

config = configparser.ConfigParser()
config.read('ccms.ini')

MQTT_BROKER = config['MQTT']['broker']
MQTT_PORT = int(config['MQTT']['port'])
MQTT_TOPIC = config['MQTT']['topic']

LOG_FILE = config['LOG']['log_file']
HASH_MISMATCH_LOG = config['LOG']['hash_mismatch_log']
LABEL = config['TEST']['label']

AES_KEY = b'\x01' * 16
CHACHA_KEY = b'\x02' * 32
SPECK_KEY = 0x123456789ABCDEF00FEDCBA987654321
SPECK_cipher = SpeckCipher(SPECK_KEY, key_size=128, block_size=128)
SPECK_block_size = SPECK_cipher.block_size // 8
ASCON_KEY = b'\x03' * 16
ASCON_NONCE = b'\x04' * 16

decompression_methods = {
    "none": lambda data: data,
    "zlib": lambda data: zlib.decompress(data),
    "gzip": lambda data: gzip.decompress(data),
    "bz2": lambda data: bz2.decompress(data),
    "lzma": lambda data: lzma.decompress(data),
    "lz4": lambda data: lz4.frame.decompress(data),
    "snappy": lambda data: snappy.uncompress(data)
}

stop_event = threading.Event()

r_code_total_time = 0.0
r_code_loop = 0
network_status = 0.0

# def get_netwok_status():
#     print(MQTT_BROKER)
#     return pping.average_ping(host=MQTT_BROKER, count=10)

def decrypt_data(enc_type, encrypted_data):
    try:
        if enc_type == "none":
            return encrypted_data
        elif enc_type == "AES-GCM":
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            aesgcm = AESGCM(AES_KEY)
            return aesgcm.decrypt(nonce, ciphertext, None)
        elif enc_type == "ChaCha20-Poly1305":
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            chacha = ChaCha20Poly1305(CHACHA_KEY)
            return chacha.decrypt(nonce, ciphertext, None)
        elif enc_type == "Speck":
            block_size_bytes = SPECK_block_size
            decrypted_blocks = []
            for i in range(0, len(encrypted_data), block_size_bytes):
                block = int.from_bytes(encrypted_data[i:i+block_size_bytes], 'big')
                decrypted = SPECK_cipher.decrypt(block)
                decrypted &= (1 << 64) - 1
                decrypted_bytes = decrypted.to_bytes(block_size_bytes, 'big')
                decrypted_blocks.append(decrypted_bytes)
            return b''.join(decrypted_blocks).rstrip(b'\x00')
        elif enc_type == "ASCON":
            return ascon.decrypt(ASCON_KEY, ASCON_NONCE, b"", encrypted_data)
        else:
            raise ValueError(f"Unsupported encryption type: {enc_type}")
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

def timing_logging(mdata):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(mdata) + "\n")

def log_hash_mismatch(metadata, actual_hash):
    metadata["actual_hash"] = actual_hash
    with open(HASH_MISMATCH_LOG, "a") as f:
        f.write(json.dumps(metadata) + "\n")

def process_message(msg):
    global r_code_total_time, r_code_loop, network_status
    receive_time = time.time()
    try:
        payload = msg.payload
        parsed = json.loads(payload.decode())

            #         metadata = {
            #     "direction": "pub",
            #     "id": id_value,
            #     "sequence": sequence_number,
            #     "pub_ping": network_status,
            #     "compress_time": compress_time,
            #     "encryption_time": encryption_time,
            #     "publish_time": time.time()
            # 
            #  meta_set = {
            #     "id": id_value,
            #     "sequence": sequence_number,
            #     "hash": hash_value,
            # }

        metadata = parsed["metadata"]    
        metadata['msize'] = len(parsed["data"])    
        encrypted_data = base64.b64decode(parsed["data"])
  
        metadata["subscribe_time"] = receive_time
        #publish_time = metadata.get("publish_time", receive_time)
        id = int(metadata.get("id"))
        metadata["compress_method"], metadata["encryption_type"], hash_flag = get_configuration_by_id(id)
        metadata["hash_time"]=0.0
        if hash_flag != "none":
            hash_start = time.perf_counter()
            expected_hash = metadata.get("hash")
            actual_hash = hashlib.sha256(encrypted_data).hexdigest()
            metadata["hash_time"] = metadata.get("hash_ptime",0.0) +  time.perf_counter() - hash_start
            if expected_hash != actual_hash:
                print(f"[WARNING] Hash mismatch! Message may be tampered.")
                print(f"Expected: {expected_hash}")
                print(f"Actual:   {actual_hash}")
                log_hash_mismatch(metadata, actual_hash)
                return
        else:
            expected_hash=None
            metadata["hash_time"] = 0.0

        decrypt_start = time.perf_counter()
        decrypted_data = decrypt_data(metadata["encryption_type"], encrypted_data)
        if decrypted_data is None:
            print("Decryption failed. Skipping message.")
            return
        decrypt_time = time.perf_counter() - decrypt_start
        metadata["decryption_time"] = decrypt_time

        decompress_start = time.perf_counter()
        decompressed_data = decompression_methods[metadata["compress_method"]](decrypted_data)
        metadata['size'] = len(decompressed_data)
       
        decompress_time = time.perf_counter() - decompress_start
        metadata["decompress_time"] = decompress_time

        metadata["sub_ping"] = network_status
        #rtt = receive_time - publish_time
        #etadata["subscribe_time"] =  decrypt_time + decompress_time + metadata["hash_time"]

        print(f"Received: id={id}, Seq={metadata['sequence']}, Compress Method={metadata['compress_method']}, Encryption={metadata['encryption_type']}")
        print(f"Size: {metadata['size']}, Subscribe Time: {metadata['subscribe_time']:.6f} sec")
        #metadata["direction"] = "sub"

               # id를 선두에 위치시키는 새로운 딕셔너리 생성
        ordered_metadata = {"direction": "sub"}
        ordered_metadata.update(metadata)
        metadata = ordered_metadata

        timing_logging(metadata)

    except Exception as e:
        print(f"Error processing message: {e}")

def on_message(client, userdata, msg):
    threading.Thread(target=process_message, args=(msg,)).start()

def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(MQTT_TOPIC)

def start_subscriber(stop_event):
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 100)
    client.loop_start()
    print("Subscriber started. Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    finally:
        client.loop_stop()
        client.disconnect()
        print("MQTT disconnected.")

if __name__ == "__main__":
    #network_status = get_netwok_status()
    print(f"Loop {r_code_loop}, Network Status: {network_status} sec")

    subscriber_thread = threading.Thread(target=start_subscriber, args=(stop_event,))
    subscriber_thread.start()
    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopping subscriber...")
        stop_event.set()
    subscriber_thread.join()
    print("Subscriber stopped.")
