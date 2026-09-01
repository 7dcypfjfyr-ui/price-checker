"""Adaptable price extraction.

Strategy (in order, best signal first). We never rely on one hard-coded
selector or a magic number in a specific script tag:

  1. JSON-LD  (schema.org Product / Offer / AggregateOffer)  -- highest trust
  2. Microdata (itemprop="price")
  3. Meta tags (og:price:amount, product:price:amount, itemprop=price ...)
  4. Attributes commonly holding a machine price (data-price, content=...)
  5. Visible-text heuristic: currency-shaped numbers, scored by nearby
     keywords ("price", "sale", "now", "add to cart") and DOM prominence.

If plain HTTP yields nothing trustworthy, the page is re-fetched with a
headless browser (Playwright) so client-rendered prices become visible,
and steps 1-5 run again on the rendered DOM.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup

from .priceparse import parse_price, guess_currency

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 25

PRICE_KEYWORDS = ("price", "prijs", "preis", "precio", "prezzo", "prix")
SALE_KEYWORDS = ("sale", "now", "deal", "offer", "special", "today")
NEGATIVE_KEYWORDS = (
    "shipping", "delivery", "rrp", "was", "list price", "msrp", "save",
    "tax", "vat", "/mo", "per month", "month", "installment", "financing",
    "subtotal", "total", "you save",
)


@dataclass
class PriceResult:
    ok: bool
    price: float | None = None
    currency: str | None = None
    method: str | None = None          # which strategy won
    confidence: float = 0.0            # 0..1
    rendered: bool = False             # did we need the headless browser
    note: str | None = None
    candidates: list | None = None     # everything we saw, for debugging

    def to_dict(self):
        d = asdict(self)
        if d.get("candidates"):
            d["candidates"] = d["candidates"][:12]
        return d


# --------------------------------------------------------------------------- #
# individual strategies -> yield (price, currency, method, confidence)
# --------------------------------------------------------------------------- #
def _walk_jsonld(node, out):
    if isinstance(node, list):
        for n in node:
            _walk_jsonld(n, out)
        return
    if not isinstance(node, dict):
        return
    if "@graph" in node:
        _walk_jsonld(node["@graph"], out)

    offers = node.get("offers")
    if offers is not None:
        for off in (offers if isinstance(offers, list) else [offers]):
            if not isinstance(off, dict):
                continue
            cur = off.get("priceCurrency") or node.get("priceCurrency")
            for key in ("price", "lowPrice", "highPrice"):
                if key in off and off[key] not in (None, ""):
                    spec = off.get("priceSpecification")
                    p, c = parse_price(off[key])
                    if p:
                        out.append((p, cur or c, f"json-ld:offers.{key}", 0.95))
            spec = off.get("priceSpecification")
            if isinstance(spec, dict) and spec.get("price"):
                p, c = parse_price(spec["price"])
                if p:
                    out.append((p, spec.get("priceCurrency") or cur or c,
                                "json-ld:priceSpecification", 0.95))
    # bare price on a Product/Offer node
    if node.get("price") not in (None, ""):
        p, c = parse_price(node["price"])
        if p:
            out.append((p, node.get("priceCurrency") or c, "json-ld:price", 0.9))

    for v in node.values():
        if isinstance(v, (dict, list)):
            _walk_jsonld(v, out)


def from_jsonld(soup: BeautifulSoup):
    out = []
    for tag in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        txt = tag.string or tag.get_text() or ""
        txt = txt.strip()
        if not txt:
            continue
        # some sites concatenate multiple JSON objects
        for chunk in _split_json_objects(txt):
            try:
                data = json.loads(chunk)
            except Exception:
                continue
            _walk_jsonld(data, out)
    return out


def _split_json_objects(txt):
    txt = txt.strip()
    try:
        json.loads(txt)
        return [txt]
    except Exception:
        pass
    objs, depth, start = [], 0, None
    for i, ch in enumerate(txt):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(txt[start:i + 1])
                start = None
    return objs or [txt]


def from_microdata(soup: BeautifulSoup):
    out = []
    for el in soup.select('[itemprop="price"], [itemprop="lowPrice"]'):
        raw = el.get("content") or el.get("value") or el.get_text(" ", strip=True)
        p, c = parse_price(raw)
        if p:
            cur_el = el.find_parent().select_one('[itemprop="priceCurrency"]') if el.find_parent() else None
            cur = None
            if cur_el:
                cur = cur_el.get("content") or cur_el.get_text(strip=True)
            out.append((p, cur or c, "microdata:itemprop=price", 0.85))
    return out


META_PRICE_KEYS = [
    ("property", "product:price:amount"),
    ("property", "og:price:amount"),
    ("property", "og:product:price:amount"),
    ("name", "twitter:data1"),
    ("itemprop", "price"),
    ("name", "price"),
]
META_CUR_KEYS = [
    ("property", "product:price:currency"),
    ("property", "og:price:currency"),
    ("itemprop", "priceCurrency"),
]


def from_meta(soup: BeautifulSoup):
    out = []
    cur = None
    for attr, val in META_CUR_KEYS:
        el = soup.find("meta", attrs={attr: val})
        if el and el.get("content"):
            cur = el["content"].strip()
            break
    for attr, val in META_PRICE_KEYS:
        el = soup.find("meta", attrs={attr: val})
        if el and el.get("content"):
            p, c = parse_price(el["content"])
            if p:
                conf = 0.8 if "price" in val else 0.55
                out.append((p, cur or c, f"meta:{val}", conf))
    return out


PRICE_ATTR_RE = re.compile(r"(data-)?(product-?)?price(-amount)?$", re.I)


def from_attributes(soup: BeautifulSoup):
    out = []
    for el in soup.find_all(True):
        for name, val in el.attrs.items():
            if not isinstance(val, str):
                continue
            if PRICE_ATTR_RE.search(name) and any(ch.isdigit() for ch in val):
                p, c = parse_price(val)
                if p:
                    out.append((p, c, f"attr:{name}", 0.55))
    return out


CURRENCY_TEXT_RE = re.compile(
    r"(?:US\$|R\$|C\$|A\$|MX\$|[$€£¥₹]|\b(?:USD|EUR|GBP|JPY|INR|BRL|CAD|AUD|CHF|SEK|PLN|MXN|NZD|SGD)\b)\s?"
    r"\d[\d.,   ]*\d|\d[\d.,   ]*\d\s?(?:US\$|R\$|[$€£¥₹]|\b(?:USD|EUR|GBP|JPY|INR|BRL|kr|zł)\b)",
    re.I,
)


def from_text_heuristic(soup: BeautifulSoup):
    """Scan visible text for currency-shaped numbers and score them."""
    for bad in soup(["script", "style", "noscript", "template"]):
        bad.decompose()

    scored = []
    for el in soup.find_all(string=CURRENCY_TEXT_RE):
        parent = el.parent
        if parent is None:
            continue
        context = " ".join(
            filter(None, [
                (parent.get("class") and " ".join(parent.get("class"))) or "",
                parent.get("id") or "",
                parent.get("itemprop") or "",
                (parent.parent.get("class") and " ".join(parent.parent.get("class"))) if parent.parent else "",
            ])
        ).lower()
        nearby = str(el).lower()
        # a little surrounding text
        prev = (parent.find_previous(string=True) or "")[-60:].lower()

        for match in CURRENCY_TEXT_RE.finditer(str(el)):
            p, c = parse_price(match.group(0))
            if not p:
                continue
            score = 0.30
            blob = context + " " + nearby + " " + prev
            if any(k in blob for k in PRICE_KEYWORDS):
                score += 0.20
            if any(k in blob for k in SALE_KEYWORDS):
                score += 0.08
            if any(k in blob for k in NEGATIVE_KEYWORDS):
                score -= 0.25
            # prominent tags / attributes
            if parent.name in ("h1", "h2", "span", "div", "p", "strong", "b"):
                score += 0.03
            if parent.get("itemprop") == "price":
                score += 0.25
            tagline = " ".join(t.name for t in parent.parents if t.name)
            score = max(0.05, min(score, 0.75))
            scored.append((p, c or guess_currency(str(el)),
                           "text-heuristic", round(score, 3)))
    return scored


STRATEGIES = [
    ("json-ld", from_jsonld),
    ("microdata", from_microdata),
    ("meta", from_meta),
    ("attributes", from_attributes),
    ("text", from_text_heuristic),
]


def _collect(html: str):
    soup = BeautifulSoup(html, "lxml")
    cands = []
    for _name, fn in STRATEGIES:
        try:
            cands.extend(fn(BeautifulSoup(html, "lxml")))
        except Exception as exc:  # never let one strategy kill the run
            cands.append((None, None, f"error:{_name}:{exc}", 0.0))
    return [c for c in cands if c[0]]


def _pick(cands):
    """Choose the winner. Prefer high confidence; break ties by agreement."""
    if not cands:
        return None
    # cluster by rounded price, sum confidence for agreement bonus
    from collections import defaultdict
    agree = defaultdict(float)
    for price, _cur, _m, conf in cands:
        agree[round(price, 2)] += conf

    def key(c):
        price, _cur, _m, conf = c
        return (conf + 0.15 * (agree[round(price, 2)] - conf), conf)

    return max(cands, key=key)


def extract_from_html(html: str, rendered: bool = False) -> PriceResult:
    cands = _collect(html)
    winner = _pick(cands)
    if not winner:
        return PriceResult(ok=False, rendered=rendered,
                           note="no price-shaped value found",
                           candidates=[list(c) for c in cands])
    price, currency, method, conf = winner
    return PriceResult(
        ok=True, price=round(price, 2), currency=currency, method=method,
        confidence=round(conf, 3), rendered=rendered,
        candidates=[list(c) for c in sorted(cands, key=lambda c: -c[3])],
    )


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def _render_html(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_context(
                user_agent=UA, locale="en-US",
                viewport={"width": 1280, "height": 2000},
            ).new_page()
            page.goto(url, wait_until="networkidle", timeout=45_000)
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def check_url(url: str, min_confidence: float = 0.5,
              allow_render: bool = True) -> PriceResult:
    """Fetch `url` and return the best price we can find."""
    html = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        static_note = f"http fetch failed: {exc}"
        html = None
    else:
        static_note = None

    if html:
        result = extract_from_html(html, rendered=False)
        if result.ok and result.confidence >= min_confidence:
            return result
    else:
        result = PriceResult(ok=False, note=static_note)

    if allow_render:
        rendered_html = _render_html(url)
        if rendered_html:
            r2 = extract_from_html(rendered_html, rendered=True)
            # keep whichever is better
            if r2.ok and (not result.ok or r2.confidence >= result.confidence):
                return r2
            if r2.ok:
                return r2
        else:
            if not result.ok:
                result.note = (result.note or "") + " | headless render unavailable/failed"

    return result
