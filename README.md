# Price Tracker

Paste a product URL, and a GitHub Action checks its price once a day, appends it
to a price history, and publishes a dashboard with stats (all-time low/high,
average, median, % above the lowest ever, 30/90-day windows, trend, sparkline).

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
  { "id": "any-unique-string", "url": "https://example.com/product/123", "label": "Cool Thing" }
]
```

(When the checker runs it fills in a proper `id`; you can leave it and it will be
normalised. To remove something, delete its line here and its file in
`data/history/`.)

## Running it locally (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

python -m tracker.check once "https://example.com/product/123"   # one-off, prints JSON, saves nothing
python -m tracker.check add  "https://example.com/product/123" --label "Cool Thing"
python -m tracker.check run                                      # check everything, append history
python -m tracker.check build                                    # rebuild site/dashboard.json
python -m http.server -d site 8777                               # view dashboard at localhost:8777
```

`--no-render` skips the headless-browser fallback (faster, but misses JS-only prices).

## Files

| Path | Purpose |
|---|---|
| `tracker/extract.py` | strategy stack + headless-browser fallback |
| `tracker/priceparse.py` | messy-string → (amount, currency) |
| `tracker/stats.py` | history → stats for the dashboard |
| `tracker/check.py` | CLI: `add` / `list` / `remove` / `run` / `once` / `build` |
| `data/products.json` | the URLs you track |
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
- Always-low prices, big drops, and trend are shown per card; there's no email
  alert yet — easy to add in `check.py` if you want one.
