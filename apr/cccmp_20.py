import base64
import hashlib
import time
import random
import string
import zlib
import gzip
import bz2
import lzma
import lz4.frame
import snappy
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
import paho.mqtt.client as mqtt
from speck import SpeckCipher
import ascon
import pping
import configparser
from cccm_sinario import combinations_with_id

config = configparser.ConfigParser()
config.read('ccms.ini')

# 전역 변수처럼 사용
MQTT_BROKER = config['MQTT']['broker']
MQTT_PORT = int(config['MQTT']['port'])
MQTT_TOPIC = config['MQTT']['topic']

LOG_FILE = config['LOG']['log_file']
HASH_MISMATCH_LOG = config['LOG']['hash_mismatch_log']
LABEL = config['TEST']['label']
TIME_SLEEP = float(config['TEST']['time_sleep'])
TEST_LOOP = int(config['TEST']['test_loop'])

AES_KEY = b'\x01' * 16
CHACHA_KEY = b'\x02' * 32

SPECK_KEY = 0x123456789ABCDEF00FEDCBA987654321
SPECK_cipher = SpeckCipher(SPECK_KEY, key_size=128, block_size=128)
SPECK_block_size = SPECK_cipher.block_size // 8

ASCON_KEY = b'\x03' * 16
ASCON_NONCE = b'\x04' * 16

compression_methods = {
    "none": lambda data: data,
    "zlib": lambda data: zlib.compress(data),
    "gzip": lambda data: gzip.compress(data),
    "bz2": lambda data: bz2.compress(data),
    "lzma": lambda data: lzma.compress(data),
    "lz4": lambda data: lz4.frame.compress(data), #.encode('utf-8'))
    "snappy": lambda data: snappy.compress(data) 
}

def timing_logging(mdata):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(mdata) + "\n")

def get_netwok_status():
    return pping.average_ping(host=MQTT_BROKER)

def encrypt_none(data):
    return data

def encrypt_aes_gcm(data):
    nonce = os.urandom(12)
    aesgcm = AESGCM(AES_KEY)
    return nonce + aesgcm.encrypt(nonce, data, None)

def encrypt_chacha20(data):
    nonce = os.urandom(12)
    chacha = ChaCha20Poly1305(CHACHA_KEY)
    ciphertext = chacha.encrypt(nonce, data, None)
    return nonce + ciphertext

def encrypt_speck(data):
    cipher = SPECK_cipher
    block_size_bytes = SPECK_block_size
    padded = data + b'\x00' * ((block_size_bytes - len(data) % block_size_bytes) % block_size_bytes)
    encrypted_blocks = []
    for i in range(0, len(padded), block_size_bytes):
        block = int.from_bytes(padded[i:i+block_size_bytes], 'big')
        encrypted = cipher.encrypt(block)
        encrypted &= (1 << 64) - 1
        encrypted_bytes = encrypted.to_bytes(8, 'big')
        if len(encrypted_bytes) < block_size_bytes:
            encrypted_bytes = b'\x00' * (block_size_bytes - len(encrypted_bytes)) + encrypted_bytes
        encrypted_blocks.append(encrypted_bytes)
    return b''.join(encrypted_blocks)

def encrypt_ascon(data):
    return ascon.encrypt(ASCON_KEY, ASCON_NONCE, b"", data)

encryption_methods = {
    "none": encrypt_none,
    "AES-GCM": encrypt_aes_gcm,
    "ChaCha20-Poly1305": encrypt_chacha20,
   # "Speck": encrypt_speck,
    "ASCON": encrypt_ascon
}
# ... (import, config, 함수 정의 부분은 동일)
print("Broker:", MQTT_BROKER)
publisher = mqtt.Client()
try:
    publisher.connect(MQTT_BROKER, MQTT_PORT, 100)
except Exception as e:
    print(f"Failed to connect to MQTT broker: {e}")
    exit(1)

sequence_number = 0
data_sizes = [8, 16, 32, 64, 128, 256, 512, 1024, 8000, 20000, 30000, 32_768, 65_536, 131_072, 262_144, 524_288]
data_sizes = [512, 2048, 9024, 16384, 65536]
#data_sizes_old = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1496, 1500, 1600, 2048, 4096, 8012, 16024, 32048, 64096]
# data_sizes = [14, 16, 20, 24, 32, 40, 62, 128, 216, 1_024, 1_536, 2_048, 8_192, 12_288, 16_384, 
#  1_400, 1_460, 1_461, 1_500, 10_240, 50_000, 100_000, 200_000, 300_000, 500_000, 
#  1_000_000, 2_000_000, 5_000_000, 8_000_000, 20_000_000]
# data_sizes = [8, 16, 32, 64, 128, 150, 256, 512, 1_024, 
#               2_048, 4_096, 8_192, 16_384, 32_768, 65_536, 131_072, 262_144, 524_288, 
#               1_048_576, 2_097_152, 4_194_304, 8_388_608, 16_777_216, 33_554_432]
#               #67_108_864, 134_217_728, 200_000_000]
network_status = get_netwok_status()
print(f"Network Status: {network_status} sec")

for loop in range(1, TEST_LOOP + 1):
    network_status = get_netwok_status()
    print(f"Loop {loop}, Network Status: {network_status} sec")  

    for id_value, comp_method, enc_method, hash_option in combinations_with_id:
        print(f"\n=== Loop:{loop}, Processing ID={id_value}, Comp={comp_method}, Enc={enc_method}, Hash={hash_option} ===")             

        for size in data_sizes:

            # if sequence_number <=2104:
            #     sequence_number += 1
            #     continue

            start_time = time.perf_counter()
            original_data = ''.join(random.choices(string.ascii_letters + string.digits, k=size)).encode()

            try:
                compressed_data = compression_methods[comp_method](original_data)
            except Exception as e:
                print(f"Compression error: {e}")
                continue
            compress_time = time.perf_counter() - start_time
            compressed_size = len(compressed_data)

            start_enc_time = time.perf_counter()
            try:
                encrypted_data = encryption_methods[enc_method](compressed_data)
            except Exception as e:
                print(f"Encryption error: {e}")
                continue
            encryption_time = time.perf_counter() - start_enc_time

            metadata = {
                "direction": "pub",
                "id": id_value,
                "sequence": sequence_number,
                "pub_ping": network_status,
                "compress_time": compress_time,
                "encryption_time": encryption_time,
                "publish_time": time.time()
            }

            hash_time = 0.0 
            hash_value = None
            if hash_option != "none":
                start_hash_time = time.perf_counter()
                hash_value = hashlib.sha256(encrypted_data).hexdigest()
                hash_time = time.perf_counter() - start_hash_time
                metadata["hash"] = hash_value
                metadata["hash_time"] = hash_time
                print("hash:", hash_value)

            meta_set = {
                "id": id_value,
                "sequence": sequence_number,
                "hash": hash_value,
            }
            metadata["hash_time"] = hash_time

            topic = MQTT_TOPIC # #f"iot/data/{id_value}"
            payload = {
                "metadata": meta_set,
                "data": base64.b64encode(encrypted_data).decode()
            }
            send_data = json.dumps(payload).encode()
            publisher.publish(topic, send_data)
            timing_logging(metadata)
            print(f"Published: ID={id_value}, Method={comp_method}, Encryption={enc_method}, Size={size}, Seq={sequence_number}")
            time.sleep(TIME_SLEEP)
            sequence_number += 1

print("Publishing completed.")
