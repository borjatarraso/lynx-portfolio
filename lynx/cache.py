"""
Cache management helpers.
Wraps the instrument_cache table and handles TTL logic.
"""

from typing import Optional, Dict
from . import database

DEFAULT_TTL = 3600  # 1 hour


def get(ticker: str, max_age: int = DEFAULT_TTL) -> Optional[Dict]:
    """Return cached data if it exists and is within max_age seconds."""
    age = database.cache_age_seconds(ticker)
    if age is None or age > max_age:
        return None
    row = database.cache_get(ticker)
    if not row:
        return None
    # Re-map 'price' → 'current_price' for uniform interface
    row["current_price"] = row.pop("price", None)
    return row




def put(ticker: str, data: Dict) -> None:
    database.cache_put(ticker, data)


def delete(ticker: Optional[str] = None) -> int:
    return database.cache_delete(ticker)


def age(ticker: str) -> Optional[float]:
    return database.cache_age_seconds(ticker)
