import random
import time


DEFAULT_NETWORK_PROFILE = {
    "enabled": False,
    "base_delay_ms": 0.0,
    "jitter_ms": 0.0,
    "drop_rate": 0.0,
}


def normalize_network_profile(profile=None):
    if not isinstance(profile, dict):
        profile = {}

    drop_rate = float(profile.get("drop_rate", 0.0) or 0.0)
    return {
        "enabled": bool(profile.get("enabled", False)),
        "base_delay_ms": max(0.0, float(profile.get("base_delay_ms", 0.0) or 0.0)),
        "jitter_ms": max(0.0, float(profile.get("jitter_ms", 0.0) or 0.0)),
        "drop_rate": min(1.0, max(0.0, drop_rate)),
    }


def apply_network_profile(profile=None):
    normalized = normalize_network_profile(profile)
    if not normalized["enabled"]:
        return {
            "dropped": False,
            "delay_ms": 0.0,
            "profile": normalized,
        }

    delay_ms = normalized["base_delay_ms"]
    if normalized["jitter_ms"] > 0:
        delay_ms += random.uniform(0.0, normalized["jitter_ms"])
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    dropped = random.random() < normalized["drop_rate"]
    return {
        "dropped": dropped,
        "delay_ms": round(delay_ms, 3),
        "profile": normalized,
    }
