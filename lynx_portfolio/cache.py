"""
Cache management helpers.
Wraps the instrument_cache table and handles TTL logic.
"""

from datetime import datetime
from typing import Optional, Dict
from . import database

DEFAULT_TTL = 3600  # 1 hour


def get(ticker: str, max_age: int = DEFAULT_TTL) -> Optional[Dict]:
    """Return cached data if it exists and is within max_age seconds."""
    try:
        row = database.cache_get(ticker)
    except Exception:
        return None
    if not row or not row.get("cached_at"):
        return None
    try:
        cached_at = datetime.fromisoformat(row["cached_at"])
    except (ValueError, TypeError):
        # Malformed timestamp — treat as cache miss
        return None
    age = (datetime.now() - cached_at).total_seconds()
    if age > max_age:
        return None
    # Re-map 'price' → 'current_price' for uniform interface
    result = dict(row)
    result["current_price"] = result.pop("price", None)
    return result


def put(ticker: str, data: Dict) -> None:
    try:
        database.cache_put(ticker, data)
    except Exception:
        pass  # cache write failure is non-fatal


def delete(ticker: Optional[str] = None) -> int:
    try:
        return database.cache_delete(ticker)
    except Exception:
        return 0


def age(ticker: str) -> Optional[float]:
    try:
        return database.cache_age_seconds(ticker)
    except Exception:
        return None
