combinations_with_id = [
    (1, "none", "none", "none"), (2, "none", "none", "hash"),
    (3, "none", "AES-GCM", "none"), (4, "none", "AES-GCM", "hash"),
    (5, "none", "ChaCha20-Poly1305", "none"), (6, "none", "ChaCha20-Poly1305", "hash"),
    (7, "none", "ASCON", "none"), (8, "none", "ASCON", "hash"),
    
    (9, "zlib", "none", "none"), (10, "zlib", "none", "hash"),
    (11, "zlib", "AES-GCM", "none"), (12, "zlib", "AES-GCM", "hash"),
    (13, "zlib", "ChaCha20-Poly1305", "none"), (14, "zlib", "ChaCha20-Poly1305", "hash"),
    (15, "zlib", "ASCON", "none"), (16, "zlib", "ASCON", "hash"),

    (17, "gzip", "none", "none"), (18, "gzip", "none", "hash"),
    (19, "gzip", "AES-GCM", "none"), (20, "gzip", "AES-GCM", "hash"),
    (21, "gzip", "ChaCha20-Poly1305", "none"), (22, "gzip", "ChaCha20-Poly1305", "hash"),
    (23, "gzip", "ASCON", "none"), (24, "gzip", "ASCON", "hash"),

    (25, "bz2", "none", "none"), (26, "bz2", "none", "hash"),
    (27, "bz2", "AES-GCM", "none"), (28, "bz2", "AES-GCM", "hash"),
    (29, "bz2", "ChaCha20-Poly1305", "none"), (30, "bz2", "ChaCha20-Poly1305", "hash"),
    (31, "bz2", "ASCON", "none"), (32, "bz2", "ASCON", "hash"),

    (33, "lzma", "none", "none"), (34, "lzma", "none", "hash"),
    (35, "lzma", "AES-GCM", "none"), (36, "lzma", "AES-GCM", "hash"),
    (37, "lzma", "ChaCha20-Poly1305", "none"), (38, "lzma", "ChaCha20-Poly1305", "hash"),
    (39, "lzma", "ASCON", "none"), (40, "lzma", "ASCON", "hash"),

    (41, "lz4", "none", "none"), (42, "lz4", "none", "hash"),
    (43, "lz4", "AES-GCM", "none"), (44, "lz4", "AES-GCM", "hash"),
    (45, "lz4", "ChaCha20-Poly1305", "none"), (46, "lz4", "ChaCha20-Poly1305", "hash"),
    (47, "lz4", "ASCON", "none"), (48, "lz4", "ASCON", "hash"),

    (49, "snappy", "none", "none"), (50, "snappy", "none", "hash"),
    (51, "snappy", "AES-GCM", "none"), (52, "snappy", "AES-GCM", "hash"),
    (53, "snappy", "ChaCha20-Poly1305", "none"), (54, "snappy", "ChaCha20-Poly1305", "hash"),
    (55, "snappy", "ASCON", "none"), (56, "snappy", "ASCON", "hash"),
]

def get_configuration_by_id(id_value):
    for combo in combinations_with_id:
        if combo[0] == id_value:
            return combo[1], combo[2], combo[3]
    return None, None, None  # id가 존재하지 않을 경우, 'compression': 'zlib', 'encryption': 'AES-GCM', 'hash': 'hash'}
