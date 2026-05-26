import base64
import gzip
import hashlib
import json
import os
import zlib
from datetime import datetime, timezone
from typing import Any

def _load_aes_key() -> bytes:
    key_hex = os.getenv("APR_AES_KEY_HEX", "")
    if key_hex:
        key = bytes.fromhex(key_hex)
        if len(key) not in (16, 24, 32):
            raise ValueError("APR_AES_KEY_HEX must decode to 16, 24, or 32 bytes")
        return key
    return b"\x01" * 16


AES_KEY = _load_aes_key()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compress_data(method: str, data_bytes: bytes) -> bytes:
    if method == "zlib":
        return zlib.compress(data_bytes)
    if method == "gzip":
        return gzip.compress(data_bytes)
    return data_bytes


def decompress_data(method: str, compressed_bytes: bytes) -> bytes:
    if method == "zlib":
        return zlib.decompress(compressed_bytes)
    if method == "gzip":
        return gzip.decompress(compressed_bytes)
    return compressed_bytes


def encrypt_data(method: str, data_bytes: bytes) -> bytes:
    if method == "AES-GCM":
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        aesgcm = AESGCM(AES_KEY)
        encrypted = aesgcm.encrypt(nonce, data_bytes, None)
        return nonce + encrypted
    return data_bytes


def decrypt_data(method: str, encrypted_bytes: bytes) -> bytes:
    if method == "AES-GCM":
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(encrypted_bytes) < 12:
            raise ValueError("AES-GCM encrypted data too short for nonce")
        nonce = encrypted_bytes[:12]
        ciphertext = encrypted_bytes[12:]
        aesgcm = AESGCM(AES_KEY)
        return aesgcm.decrypt(nonce, ciphertext, None)
    return encrypted_bytes


def encode_payload(data: Any, policy: dict, seq: int = 0, experiment_id: str | None = None) -> dict:
    raw_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    comp_method = policy.get("compression", "none")
    compressed = compress_data(comp_method, raw_json)

    enc_method = policy.get("encryption", "none")
    encrypted = encrypt_data(enc_method, compressed)

    hash_method = policy.get("integrity", "none")
    hash_value = None
    if hash_method == "sha256":
        hash_value = hashlib.sha256(encrypted).hexdigest()

    metadata = {
        "publish_timestamp": now_iso(),
        "experiment_id": experiment_id,
        "seq": seq,
        "qos": int(policy.get("qos", 0)),
        "compression": comp_method,
        "encryption": enc_method,
        "integrity": hash_method,
        "hash": hash_value,
    }

    encoded_data = base64.b64encode(encrypted).decode("utf-8")
    return {"metadata": metadata, "data": encoded_data}


def decode_payload(metadata: dict, encoded_data_str: str) -> Any:
    encrypted_bytes = base64.b64decode(encoded_data_str)

    hash_method = metadata.get("integrity", "none")
    if hash_method == "sha256":
        expected_hash = metadata.get("hash")
        actual_hash = hashlib.sha256(encrypted_bytes).hexdigest()
        if expected_hash != actual_hash:
            raise ValueError(f"Integrity check failed. Expected: {expected_hash}, Actual: {actual_hash}")

    enc_method = metadata.get("encryption", "none")
    compressed_bytes = decrypt_data(enc_method, encrypted_bytes)

    comp_method = metadata.get("compression", "none")
    raw_json_bytes = decompress_data(comp_method, compressed_bytes)
    return json.loads(raw_json_bytes.decode("utf-8"))
