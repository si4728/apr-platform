import os

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _SECRET_KEY = AESGCM.generate_key(bit_length=256)
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

def apply_encryption(data_bytes: bytes, algorithm: str) -> bytes:
    if algorithm == "AES-GCM":
        if _HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(_SECRET_KEY)
            nonce = os.urandom(12)
            ct = aesgcm.encrypt(nonce, data_bytes, None)
            return nonce + ct
        else:
            # Mock encryption for experimental validation if library is missing
            return b"MOCK_AES:" + data_bytes
    return data_bytes

def remove_encryption(data_bytes: bytes, algorithm: str) -> bytes:
    if algorithm == "AES-GCM":
        if _HAS_CRYPTOGRAPHY:
            aesgcm = AESGCM(_SECRET_KEY)
            nonce = data_bytes[:12]
            ct = data_bytes[12:]
            return aesgcm.decrypt(nonce, ct, None)
        else:
            if data_bytes.startswith(b"MOCK_AES:"):
                return data_bytes[9:]
    return data_bytes
