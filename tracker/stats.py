"""Compute price-history statistics for the dashboard."""
from __future__ import annotations

import statistics
from datetime import datetime, timezone, timedelta


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def compute(history: list[dict]) -> dict:
    """history: [{"date": iso8601, "price": float, "currency": str, ...}, ...]

    Only entries with a numeric price count toward stats.
    """
    points = [
        {"date": h["date"], "price": float(h["price"]),
         "currency": h.get("currency")}
        for h in history
        if h.get("price") is not None
    ]
    points.sort(key=lambda p: p["date"])

    if not points:
        return {
            "data_points": 0,
            "current": None,
            "note": "no successful price reads yet",
        }

    prices = [p["price"] for p in points]
    current = prices[-1]
    previous = prices[-2] if len(prices) > 1 else None
    all_low = min(prices)
    all_high = max(prices)

    now = datetime.now(timezone.utc)

    def window(days):
        cutoff = now - timedelta(days=days)
        vals = [p["price"] for p in points if _parse_dt(p["date"]) >= cutoff]
        if not vals:
            return None
        return {"min": min(vals), "max": max(vals),
                "avg": round(statistics.fmean(vals), 2), "n": len(vals)}

    change_abs = round(current - previous, 2) if previous is not None else None
    change_pct = (
        round((current - previous) / previous * 100, 2)
        if previous not in (None, 0) else None
    )
    off_low_pct = (
        round((current - all_low) / all_low * 100, 2) if all_low else 0.0
    )

    # simple linear trend over last up-to-14 points
    tail = prices[-14:]
    trend = "flat"
    if len(tail) >= 3:
        first_half = statistics.fmean(tail[: len(tail) // 2])
        last_half = statistics.fmean(tail[len(tail) // 2:])
        if last_half > first_half * 1.02:
            trend = "rising"
        elif last_half < first_half * 0.98:
            trend = "falling"

    return {
        "data_points": len(points),
        "currency": points[-1]["currency"],
        "tracking_since": points[0]["date"],
        "last_checked": points[-1]["date"],
        "current": round(current, 2),
        "previous": round(previous, 2) if previous is not None else None,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "all_time_low": round(all_low, 2),
        "all_time_high": round(all_high, 2),
        "average": round(statistics.fmean(prices), 2),
        "median": round(statistics.median(prices), 2),
        "stdev": round(statistics.pstdev(prices), 2) if len(prices) > 1 else 0.0,
        "pct_above_all_time_low": off_low_pct,
        "is_all_time_low": current <= all_low + 1e-9,
        "dropped_since_last": bool(previous is not None and current < previous),
        "window_30d": window(30),
        "window_90d": window(90),
        "trend": trend,
        "series": points,
    }
