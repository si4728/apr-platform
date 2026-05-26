import hashlib

def generate_integrity_hash(data_bytes: bytes, algorithm: str) -> str:
    if algorithm == "sha256":
        return hashlib.sha256(data_bytes).hexdigest()
    elif algorithm == "md5":
        return hashlib.md5(data_bytes).hexdigest()
    return ""

def verify_integrity(data_bytes: bytes, algorithm: str, expected_hash: str) -> bool:
    if algorithm == "none" or not expected_hash:
        return True
    return generate_integrity_hash(data_bytes, algorithm) == expected_hash
