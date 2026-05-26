import math

def compute_percentile(values: list, p: float):
    if not values:
        return None
    s_vals = sorted(values)
    idx = int(round((len(s_vals) - 1) * p))
    return round(s_vals[idx], 6)

def compute_latency_stats(latencies: list) -> dict:
    if not latencies:
        return {}
        
    s_vals = sorted(latencies)
    n = len(s_vals)
    avg = sum(s_vals) / n
    return {
        "count": n,
        "min": round(s_vals[0], 6),
        "max": round(s_vals[-1], 6),
        "avg": round(avg, 6),
        "median": compute_percentile(s_vals, 0.50),
        "p95": compute_percentile(s_vals, 0.95),
        "p99": compute_percentile(s_vals, 0.99)
    }

def generate_histogram(latencies: list, bins: int = 10) -> list:
    """Generates a simple histogram for latency distribution."""
    if not latencies or bins <= 0:
        return []
        
    min_val = min(latencies)
    max_val = max(latencies)
    
    if min_val == max_val:
        return [{"bin_start": min_val, "bin_end": max_val, "count": len(latencies)}]
        
    bin_size = (max_val - min_val) / bins
    histogram = [{"bin_start": round(min_val + i*bin_size, 6), "bin_end": round(min_val + (i+1)*bin_size, 6), "count": 0} for i in range(bins)]
    
    for val in latencies:
        idx = int((val - min_val) / bin_size)
        if idx >= bins:
            idx = bins - 1
        histogram[idx]["count"] += 1
        
    return histogram

def compute_latency_trend(latencies: list, window_size: int = 10) -> list:
    """Computes moving average trend."""
    if not latencies or len(latencies) < window_size:
        return latencies
        
    trend = []
    for i in range(len(latencies) - window_size + 1):
        window = latencies[i:i+window_size]
        trend.append(round(sum(window) / window_size, 6))
    return trend
