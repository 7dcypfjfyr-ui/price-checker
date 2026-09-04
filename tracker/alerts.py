"""Decide when a price change is worth emailing about.

Alerts are derived from the *latest* check only, so each run emits an alert at
most once per event. The workflow turns each alert into a GitHub Issue, and
GitHub emails you because you watch the repo.

Env knobs (set in the workflow file):
  ALERT_DROP_PCT   minimum % drop vs the previous check to alert on (default 5)
  ALERT_ON_FAIL    "1" to alert when a product's check has failed 3x in a row
"""
from __future__ import annotations

import os


def _f(env, default):
    try:
        return float(os.environ.get(env, "") or default)
    except ValueError:
        return default


def _money(v, cur):
    c = (cur or "").upper()
    sym = {"USD": "$", "AUD": "A$", "CAD": "C$", "GBP": "£", "EUR": "€",
           "NZD": "NZ$", "JPY": "¥", "INR": "₹"}.get(c, "")
    return f"{sym}{v:,.2f}" + (f" {c}" if not sym and c else "")


def find_alerts(product: dict, history: list[dict]) -> list[dict]:
    label = product.get("label") or product["url"]
    url = product["url"]
    priced = [h for h in history if h.get("ok") and h.get("price") is not None]
    out: list[dict] = []

    # --- target price reached (only on the crossing) --------------------
    target = product.get("target")
    if target is not None and priced:
        try:
            target = float(target)
        except (TypeError, ValueError):
            target = None
    if target is not None and priced and priced[-1]["price"] <= target:
        prev_above = len(priced) < 2 or priced[-2]["price"] > target
        if prev_above:
            last = priced[-1]
            cur = last.get("currency")
            out.append({
                "kind": "target",
                "title": f"\U0001f3af Target hit: {label} — {_money(last['price'], cur)} "
                         f"(target {_money(target, cur)})",
                "body": (
                    f"**{label}** reached your target price.\n\n"
                    f"| | |\n|---|---|\n"
                    f"| Now | **{_money(last['price'], cur)}** |\n"
                    f"| Your target | {_money(target, cur)} |\n\n"
                    f"[Open product page]({url})\n\n"
                    f"_Auto-generated. Close this once you've decided._"
                ),
            })

    # --- price drop ------------------------------------------------------
    # One rule: the latest check is >= ALERT_DROP_PCT below the previous check.
    # Labelled an all-time low when it's also the lowest we've ever seen.
    # Skipped if we already emitted a target-hit for this same check.
    if len(priced) >= 2 and not any(a["kind"] == "target" for a in out):
        last, prev = priced[-1], priced[-2]
        cur = last.get("currency") or prev.get("currency")
        lo = min(h["price"] for h in priced)
        threshold = _f("ALERT_DROP_PCT", 5.0)
        drop_pct = (prev["price"] - last["price"]) / prev["price"] * 100 if prev["price"] else 0
        is_atl = last["price"] <= lo + 1e-9

        if last["price"] < prev["price"] and drop_pct >= threshold:
            emoji, tag = ("\U0001f525", "All-time low") if is_atl else ("\U0001f4b0", "Price drop")
            out.append({
                "kind": "all-time-low" if is_atl else "drop",
                "title": f"{emoji} {tag}: {label} — {_money(last['price'], cur)} "
                         f"(was {_money(prev['price'], cur)})",
                "body": (
                    f"**{label}** dropped {drop_pct:.1f}% since the last check"
                    + (" — the lowest price since tracking began." if is_atl else ".") + "\n\n"
                    f"| | |\n|---|---|\n"
                    f"| Now | **{_money(last['price'], cur)}** |\n"
                    f"| Previous check | {_money(prev['price'], cur)} |\n"
                    f"| All-time low | {_money(lo, cur)} |\n"
                    f"| Points tracked | {len(priced)} |\n\n"
                    f"[Open product page]({url})\n\n"
                    f"_Alert threshold: {threshold:g}% drop. Auto-generated; close when you're done._"
                ),
            })

    # --- tracking broke ---------------------------------------------------
    if os.environ.get("ALERT_ON_FAIL") == "1" and len(history) >= 4:
        tail = history[-3:]
        before = history[-4]
        if all(not h.get("ok") for h in tail) and before.get("ok"):
            note = tail[-1].get("note") or "unknown error"
            out.append({
                "kind": "broken",
                "title": f"⚠️ Price check failing: {label}",
                "body": (
                    f"The last 3 checks for **{label}** could not read a price.\n\n"
                    f"Most recent note:\n```\n{note}\n```\n\n"
                    f"[Open product page]({url}) — the site may have changed, "
                    f"added bot protection, or the product may be gone.\n\n"
                    f"_Auto-generated. Close this once it recovers._"
                ),
            })

    for a in out:
        a["id"] = product["id"]
    return out
