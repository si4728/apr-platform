import gzip
import zlib

def apply_compression(data_bytes: bytes, algorithm: str) -> bytes:
    if algorithm == "gzip":
        return gzip.compress(data_bytes)
    elif algorithm == "zlib":
        return zlib.compress(data_bytes)
    return data_bytes

def remove_compression(data_bytes: bytes, algorithm: str) -> bytes:
    if algorithm == "gzip":
        return gzip.decompress(data_bytes)
    elif algorithm == "zlib":
        return zlib.decompress(data_bytes)
    return data_bytes
