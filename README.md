# Price Tracker

Paste a product URL, and a GitHub Action checks its price once a day, appends it
to a price history, and publishes an interactive dashboard — per-product charts,
all-time low/high, average, median, % above the lowest ever, 30/90-day windows,
trend, target prices — plus an email when something drops.

Nothing runs on your computer. GitHub Actions is the scheduler, the repo is the
database, GitHub Pages is the dashboard. All on free tiers.

## How the price is found (adaptable, not a hard-coded number)

`tracker/extract.py` tries several strategies, best signal first, and never
depends on one CSS selector or "the 3rd number in some script tag":

1. **JSON-LD** – `schema.org` `Product` / `Offer` / `AggregateOffer` blocks
2. **Microdata** – `itemprop="price"`
3. **Meta tags** – `product:price:amount`, `og:price:amount`, `itemprop=price`, …
4. **Machine attributes** – `data-price`, `content="..."` on price-ish nodes
5. **Visible-text heuristic** – currency-shaped numbers, scored by nearby words
   ("price", "sale" boost; "shipping", "was", "/mo", "tax" penalise) and by how
   prominent the element is

Each hit is a candidate with a confidence score. Candidates that agree on the
same amount reinforce each other, and the best one wins.

**If plain HTTP finds nothing trustworthy** (confidence < 0.5), the page is
re-fetched with a headless browser (Playwright/Chromium) so JavaScript-rendered
prices become visible, and all five strategies run again on the rendered DOM.
That is why the price still gets picked up on sites where "it doesn't appear in
the script".

Number parsing (`tracker/priceparse.py`) handles `$1,299.00`, `1.299,00 €`,
`1 234,56 kr`, `USD 1299`, etc., and guesses the currency.

## One-time setup

1. Create a new GitHub repo and put these files in it (default branch `main`).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.**
4. Push. The workflow runs on push, and then daily at ~06:17 UTC.
   Your dashboard: `https://<you>.github.io/<repo>/`

## Adding / removing a URL to track

**Easiest:** Actions tab → *check-prices* → *Run workflow* → paste the URL into
`add_url` (and an optional `label`). It's added, checked, and the dashboard
updates.

**Or edit `data/products.json`** and commit:

```json
[
  { "id": "any-unique-string", "url": "https://example.com/product/123", "label": "Cool Thing", "target": 99.00 }
]
```

`target` is optional — the price you'd be happy to pay. When a check comes in at
or below it you get an email (see below), and the dashboard flags the card.

To remove something, delete its line here and its file in `data/history/`.

## The dashboard

`https://<you>.github.io/<repo>/` — refreshed after every check.

- **Summary strip** — how many tracked, at an all-time low, at target, biggest recent drop, how many need attention.
- **Sort & filter** — biggest drop, closest to target, furthest above all-time low, price, name, recently added.
- **Cards** — current price, change since last check, a chart with the all-time-low line and your target line, key stats.
- **Click a card** for the detail view — big interactive chart (hover for the price on any day, 30d / 90d / all ranges), every stat, the full price-history table, and a target-price editor.

Setting a target in the dashboard saves it **in that browser only**. To make a
target drive the email alert, put it in `data/products.json` (or use the
`target` input when running the workflow, or `tracker.check target`).

## Running it locally (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

python -m tracker.check once "https://example.com/product/123"   # one-off, prints JSON, saves nothing
python -m tracker.check add  "https://example.com/product/123" --label "Cool Thing" --target 99
python -m tracker.check target <id-or-url> 89                     # set/change a target ('none' to clear)
python -m tracker.check run                                      # check everything, append history
python -m tracker.check build                                    # rebuild site/dashboard.json
python -m tracker.check alerts                                   # print the alerts the last run would raise
python -m http.server -d site 8777                               # view dashboard at localhost:8777
```

`--no-render` skips the headless-browser fallback (faster, but misses JS-only prices).

## Files

| Path | Purpose |
|---|---|
| `tracker/extract.py` | strategy stack + headless-browser fallback |
| `tracker/priceparse.py` | messy-string → (amount, currency) |
| `tracker/stats.py` | history → stats for the dashboard |
| `tracker/alerts.py` | history → price-drop / target / failure alerts |
| `tracker/check.py` | CLI: `add` / `target` / `list` / `remove` / `run` / `once` / `build` / `alerts` |
| `data/products.json` | the URLs you track (and optional `target` prices) |
| `data/history/<id>.json` | append-only price log per product (one file = small diffs, no merge conflicts) |
| `site/` | static dashboard published to GitHub Pages |
| `.github/workflows/check-prices.yml` | daily cron + commit history + deploy Pages |

## Notes & limits

- GitHub disables scheduled workflows after 60 days of no repo activity; the
  daily commit of new prices keeps it alive.
- Some retailers (Amazon in particular) block datacenter IPs or show a captcha to
  headless browsers. The checker records a failed entry with a note rather than a
  wrong number, and the dashboard shows "last check failed". Sites with
  structured data (most Shopify stores, many big retailers) are very reliable.
- Cron time is UTC and best-effort (GitHub may delay it under load).

## Email alerts

After each check the workflow runs `python -m tracker.check alerts`, which opens a
GitHub Issue (→ email, because you watch your own repo) when:

- **🎯 a target is hit** — the price reached the `target` set in `data/products.json`
- **🔥 / 💰 a price drops** — the latest check is at least `ALERT_DROP_PCT` % below
  the previous one (🔥 if it's also the lowest price ever seen)
- **⚠️ a check keeps failing** — 3 checks in a row couldn't read a price (`ALERT_ON_FAIL`)

Each fires only on the transition, so you get one email per event, not one a day.

Tune it at the top of `.github/workflows/check-prices.yml`:

```yaml
env:
  ALERT_DROP_PCT: "5"    # minimum % drop between checks to alert on
  ALERT_ON_FAIL: "1"     # also alert after 3 straight failed checks for a product
```

Duplicate issues are suppressed (same title while still open). Close an issue
once you've acted on it; a further drop opens a new one.

**To actually receive the email:** on the repo page click **Watch → All Activity**
(or **Custom → Issues**), and make sure email is on at
<https://github.com/settings/notifications> under "Watching".
