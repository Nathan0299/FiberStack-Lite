"""
ETL Data Normalization Module.
Day 21: Provides explicit normalization functions for probe metrics.
"""
from typing import Any, Dict
from datetime import datetime
import logging

logger = logging.getLogger("fiber-etl.normalizer")


def to_float(value: Any, default: float = 0.0) -> float:
    """Convert any value to float, with fallback."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            logger.warning(f"Cannot convert '{value}' to float, using default")
            return default
    return default


def to_timestamp(value: Any) -> datetime:
    """Convert any value to datetime object."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Invalid timestamp '{value}', using now")
            return datetime.now(tz=None)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    return datetime.now(tz=None)


def normalize_metric(raw: Dict) -> Dict:
    """
    Normalize a raw metric dictionary.
    
    Handles:
    - String-to-float conversion
    - Null/missing values → defaults
    - Invalid timestamps → current time
    - Value clamping (0-100% range)
    - Metadata normalization
    """
    return {
        "node_id": str(raw.get("node_id", "unknown")),
        "country": str(raw.get("country", "XX"))[:2].upper(),
        "region": str(raw.get("region", "Unknown")),
        "latency_ms": max(0.0, to_float(raw.get("latency_ms"), 0.0)),
        "uptime_pct": min(100.0, max(0.0, to_float(raw.get("uptime_pct"), 100.0))),
        "packet_loss": min(100.0, max(0.0, to_float(raw.get("packet_loss"), 0.0))),
        "timestamp": to_timestamp(raw.get("timestamp")).isoformat(),
        "metadata": normalize_metadata(raw.get("metadata", {})),
    }


def normalize_metadata(meta: Any) -> Dict:
    """Normalize metadata dict, converting all numeric values."""
    if not isinstance(meta, dict):
        return {}
    return {k: to_float(v) if _is_numeric_key(k) else v for k, v in meta.items()}


def _is_numeric_key(key: str) -> bool:
    """Check if metadata key should be numeric."""
    numeric_suffixes = ("_percent", "_pct", "_ms", "_count", "_bytes")
    return any(key.endswith(s) for s in numeric_suffixes)


def validate_metric(metric: Dict) -> bool:
    """Validate normalized metric has all required fields with valid values."""
    required = ["node_id", "latency_ms", "uptime_pct", "packet_loss", "timestamp"]
    if not all(k in metric for k in required):
        return False
    if not isinstance(metric["timestamp"], str):
        return False
    if metric["latency_ms"] < 0:
        return False
    return True
