"""Turn messy human price strings into a float + currency guess."""
from __future__ import annotations

import re

CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR",
    "£": "GBP", "gbp": "GBP",
    "¥": "JPY", "jpy": "JPY", "yen": "JPY",
    "₹": "INR", "inr": "INR", "rs": "INR", "rs.": "INR",
    "r$": "BRL", "brl": "BRL",
    "chf": "CHF", "kr": "SEK", "zł": "PLN", "pln": "PLN",
    "c$": "CAD", "cad": "CAD", "a$": "AUD", "aud": "AUD",
    "mx$": "MXN", "mxn": "MXN",
}

# a run of digits with , . spaces or non-breaking spaces inside
_NUM_RE = re.compile(r"\d[\d.,   ]*\d|\d")


def guess_currency(text: str) -> str | None:
    if not text:
        return None
    low = text.lower()
    for token, code in CURRENCY_SYMBOLS.items():
        if token in low:
            return code
    m = re.search(r"\b([A-Z]{3})\b", text)
    if m and m.group(1) in {
        "USD", "EUR", "GBP", "JPY", "INR", "BRL", "CHF", "SEK", "PLN",
        "CAD", "AUD", "MXN", "NZD", "SGD", "HKD", "NOK", "DKK", "CZK", "ZAR",
    }:
        return m.group(1)
    return None


def _normalize_number(raw: str) -> float | None:
    """Handle 1,234.56 / 1.234,56 / 1 234,56 / 1234 / 1.299 ambiguity."""
    s = raw.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    if not s:
        return None
    has_comma = "," in s
    has_dot = "." in s

    if has_comma and has_dot:
        # whichever separator comes last is the decimal separator
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif has_comma:
        # only commas
        if re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")            # 1,234 / 12,345,678  -> thousands
        elif re.fullmatch(r"\d+,\d{2}", s):
            s = s.replace(",", ".")           # 12,99 -> decimal
        else:
            s = s.replace(",", "")
    elif has_dot:
        # only dots
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")            # 1.234 / 1.234.567 -> thousands
        # else already a normal decimal or integer
    try:
        val = float(s)
    except ValueError:
        return None
    return val


def parse_price(text) -> tuple[float | None, str | None]:
    """Return (amount, currency|None). amount is None if nothing plausible found."""
    if text is None:
        return None, None
    text = str(text)
    currency = guess_currency(text)
    best = None
    for m in _NUM_RE.finditer(text):
        val = _normalize_number(m.group(0))
        if val is None or val <= 0 or val > 100_000_000:
            continue
        # prefer the first plausible monetary-looking number
        if best is None:
            best = val
    return best, currency
