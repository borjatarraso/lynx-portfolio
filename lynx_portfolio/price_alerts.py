"""Persistent price-threshold alerts for Lynx Portfolio (v5.0).

Unlike the ad-hoc alerts in :mod:`.dashboard` (drawdown, concentration,
stale), these are *user-defined* rules. Each rule fires when the
latest ``current_price`` of a ticker crosses the configured threshold
in the configured direction. Rules persist across restarts and are
checked on every refresh; the first trigger stamps ``triggered_at``
so the user isn't paged again until they reset or delete the rule.

Condition operators (string values mirror Python):

* ``">="``  — fires when price goes **at or above** the threshold.
* ``"<="``  — fires when price goes **at or below** the threshold.
* ``">"``   — strictly above.
* ``"<"``   — strictly below.
* ``"=="``  — matches within a small epsilon (useful for intraday
  round-number targets).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import database


__all__ = [
    "PriceAlert",
    "AllowedCondition",
    "create",
    "delete",
    "list_all",
    "evaluate",
    "reset",
    "set_enabled",
    "CONDITIONS",
]

AllowedCondition = str
CONDITIONS = (">=", "<=", ">", "<", "==")
_EPS = 1e-6


@dataclass
class PriceAlert:
    id: int
    ticker: str
    condition: AllowedCondition
    threshold: float
    note: Optional[str]
    triggered_at: Optional[str]
    enabled: int
    created_at: str


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create(
    ticker: str,
    *,
    condition: AllowedCondition,
    threshold: float,
    note: Optional[str] = None,
) -> int:
    """Create a new alert rule and return its row id.

    Raises ``ValueError`` if *condition* isn't one of :data:`CONDITIONS`.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {CONDITIONS}, got {condition!r}")
    if threshold < 0:
        raise ValueError("threshold must be non-negative")
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO price_alerts (ticker, condition, threshold, note) "
            "VALUES (?, ?, ?, ?)",
            (ticker.upper(), condition, threshold, note),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete(alert_id: int) -> bool:
    conn = database.get_connection()
    try:
        cur = conn.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_all(*, ticker: Optional[str] = None) -> List[PriceAlert]:
    conn = database.get_connection()
    try:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM price_alerts WHERE ticker = ? "
                "ORDER BY id DESC",
                (ticker.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM price_alerts ORDER BY triggered_at IS NULL, id DESC",
            ).fetchall()
    finally:
        conn.close()
    return [PriceAlert(**dict(r)) for r in rows]


def reset(alert_id: int) -> bool:
    """Clear the triggered flag so the rule can fire again."""
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "UPDATE price_alerts SET triggered_at = NULL WHERE id = ?",
            (alert_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_enabled(alert_id: int, enabled: bool) -> bool:
    conn = database.get_connection()
    try:
        cur = conn.execute(
            "UPDATE price_alerts SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, alert_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------

def _matches(price: float, condition: AllowedCondition, threshold: float) -> bool:
    if condition == ">=": return price >= threshold
    if condition == "<=": return price <= threshold
    if condition == ">":  return price >  threshold
    if condition == "<":  return price <  threshold
    if condition == "==": return abs(price - threshold) <= _EPS
    return False


def evaluate(price_for: Dict[str, Optional[float]]) -> List[Dict]:
    """Evaluate every enabled rule against a price map.

    ``price_for`` maps ticker → current price (``None`` means "no data,
    skip"). Returns the list of rules that fired on this call;
    triggered rules are marked in the database so they don't fire
    again until reset.
    """
    fired: List[Dict] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = database.get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM price_alerts WHERE enabled = 1 AND triggered_at IS NULL",
        ).fetchall()
        for row in rows:
            ticker = row["ticker"]
            price = price_for.get(ticker)
            if price is None:
                continue
            if _matches(price, row["condition"], row["threshold"]):
                conn.execute(
                    "UPDATE price_alerts SET triggered_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                fired.append({
                    "id": row["id"],
                    "ticker": ticker,
                    "condition": row["condition"],
                    "threshold": row["threshold"],
                    "price": price,
                    "note": row["note"],
                    "triggered_at": now,
                })
        conn.commit()
    finally:
        conn.close()
    return fired
