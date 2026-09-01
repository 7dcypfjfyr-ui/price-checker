"""CLI entry point.

  python -m tracker.check add "https://..."        # start tracking a URL
  python -m tracker.check add "https://..." --label "Sony WH-1000XM5"
  python -m tracker.check list                       # show tracked URLs
  python -m tracker.check remove <id>
  python -m tracker.check run [--id <id>] [--no-render]   # check price(s), append history
  python -m tracker.check build                      # (re)build site/dashboard.json
  python -m tracker.check once "https://..."         # one-off check, prints result, no save
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .extract import check_url
from .stats import compute

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY_DIR = DATA / "history"
PRODUCTS_FILE = DATA / "products.json"
DASHBOARD_FILE = ROOT / "site" / "dashboard.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _pid(url: str) -> str:
    return hashlib.sha1(url.strip().encode()).hexdigest()[:10]


def load_products() -> list[dict]:
    if PRODUCTS_FILE.exists():
        return json.loads(PRODUCTS_FILE.read_text() or "[]")
    return []


def save_products(items: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    PRODUCTS_FILE.write_text(json.dumps(items, indent=2) + "\n")


def load_history(pid: str) -> list[dict]:
    f = HISTORY_DIR / f"{pid}.json"
    if f.exists():
        return json.loads(f.read_text() or "[]")
    return []


def append_history(pid: str, entry: dict) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    hist = load_history(pid)
    hist.append(entry)
    (HISTORY_DIR / f"{pid}.json").write_text(json.dumps(hist, indent=2) + "\n")


# --------------------------------------------------------------------------- #
def cmd_add(args):
    url = args.url.strip()
    items = load_products()
    pid = _pid(url)
    if any(it["id"] == pid for it in items):
        print(f"already tracking: {pid}")
        return
    items.append({
        "id": pid,
        "url": url,
        "label": args.label or "",
        "added": _now(),
    })
    save_products(items)
    print(f"added {pid}  {url}")
    if not args.no_check:
        _check_one({"id": pid, "url": url, "label": args.label or ""},
                   allow_render=not args.no_render)
        cmd_build(args)


def cmd_list(args):
    items = load_products()
    if not items:
        print("(nothing tracked yet)")
        return
    for it in items:
        hist = load_history(it["id"])
        last = hist[-1]["price"] if hist else None
        print(f'{it["id"]}  {last!s:>10}  {it["label"] or it["url"]}')


def cmd_remove(args):
    items = [it for it in load_products() if it["id"] != args.id]
    save_products(items)
    print(f"removed {args.id}")


def _check_one(item: dict, allow_render: bool) -> dict:
    url = item["url"]
    print(f"checking {item['id']}  {url}")
    res = check_url(url, allow_render=allow_render)
    entry = {
        "date": _now(),
        "price": res.price if res.ok else None,
        "currency": res.currency,
        "method": res.method,
        "confidence": res.confidence,
        "rendered": res.rendered,
        "ok": res.ok,
        "note": res.note,
    }
    append_history(item["id"], entry)
    status = (
        f"{res.price} {res.currency or ''} "
        f"via {res.method} (conf {res.confidence}"
        f"{', rendered' if res.rendered else ''})"
        if res.ok else f"FAILED: {res.note}"
    )
    print(f"  -> {status}")
    return entry


def cmd_run(args):
    items = load_products()
    if args.id:
        items = [it for it in items if it["id"] == args.id]
    if not items:
        print("nothing to check")
        return
    failures = 0
    for it in items:
        try:
            e = _check_one(it, allow_render=not args.no_render)
            failures += 0 if e["ok"] else 1
        except Exception as exc:  # keep going through the rest
            print(f"  !! error: {exc}")
            failures += 1
    cmd_build(args)
    if failures:
        print(f"{failures} of {len(items)} checks did not yield a price")


def cmd_once(args):
    res = check_url(args.url.strip(), allow_render=not args.no_render)
    print(json.dumps(res.to_dict(), indent=2))
    sys.exit(0 if res.ok else 2)


def cmd_build(args):
    items = load_products()
    out = {"generated": _now(), "products": []}
    for it in items:
        hist = load_history(it["id"])
        s = compute(hist)
        out["products"].append({
            "id": it["id"],
            "url": it["url"],
            "label": it["label"] or it["url"],
            "added": it.get("added"),
            "stats": s,
            "last_error": next(
                (h["note"] for h in reversed(hist) if not h.get("ok")), None
            ) if (hist and not hist[-1].get("ok")) else None,
        })
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {DASHBOARD_FILE.relative_to(ROOT)}  ({len(items)} products)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tracker.check")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add"); a.add_argument("url")
    a.add_argument("--label", default="")
    a.add_argument("--no-render", action="store_true")
    a.add_argument("--no-check", action="store_true")
    a.set_defaults(func=cmd_add)

    a = sub.add_parser("list"); a.set_defaults(func=cmd_list)

    a = sub.add_parser("remove"); a.add_argument("id"); a.set_defaults(func=cmd_remove)

    a = sub.add_parser("run")
    a.add_argument("--id", default=None)
    a.add_argument("--no-render", action="store_true")
    a.set_defaults(func=cmd_run)

    a = sub.add_parser("once"); a.add_argument("url")
    a.add_argument("--no-render", action="store_true")
    a.set_defaults(func=cmd_once)

    a = sub.add_parser("build"); a.set_defaults(func=cmd_build)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
