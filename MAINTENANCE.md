# Maintenance Manual

This is the operational runbook for keeping gamingapparel.gg up to date. Read
this if you're wondering "what do I actually need to do, and how often?"

**The most important fact to understand first:** the live site
(`gamingapparel.gg`) never updates itself. It only ever shows whatever
database file you last manually pushed to it. There is no cron job, no
scheduled task, and no background process running on the production server
that refreshes data. Everything described below is something *you* trigger.

---

## Quick reference: how often to do what

| Task | Frequency | Why |
|---|---|---|
| Full scrape + push to production | Weekly | Catches new products, price changes, restocks, sales |
| Spot-check the site after a scrape | Every time you scrape | Catches mistagged franchises before they go live |
| Full A-Z dropdown skim | Monthly | Catches slow-accumulating fragmentation issues that a quick glance misses |
| Code/template deploys | As needed | Only when you or I have changed `.py`/`.html`/CSS files |

---

## Weekly routine (the main one)

Do these **in this exact order**. Run everything from the
`Aggregate_Apparel_Tool` directory with your virtual environment activated.

### 1. Run the scraper
```powershell: cd "C:\Users\billi\Documents\Aggregate Site Desktop Side\Aggregate_Apparel_Tool"
py scraper.py
```
This re-scrapes all 18 automated storefronts (takes several minutes - Artsholic's
~38-page pagination crawl is the slowest part) and automatically runs
`franchise_discovery.py` afterward with its default budget (25 new Wikidata
checks per run). Do not interrupt this once it starts.

### 2. Manually refresh OceanDust
OceanDust added a Cloudflare bot-challenge in front of their `products.json`
feed that the automated scraper can't reliably get past (see
`parsers/oceandust.py` and `import_oceandust_manual.py` for the full
background), so it's excluded from `ACTIVE_PARSERS` and refreshed manually
instead, in the same weekly session:

1. In a real browser, go to `https://oceandust.co` and enter the password
   shown on the landing page (it changes over time - use whatever's
   currently displayed, not necessarily "NOSTALGIA").
2. Visit `https://oceandust.co/collections/video-games/products.json?limit=250&page=1`,
   copy the raw JSON, paste it into a new file named
   `oceandust_manual_page1.json` in the project root, and save.
3. Repeat for `page=2`, `page=3`, etc. (increment the page number) until a
   page returns `{"products": []}` - save each as `oceandust_manual_page2.json`,
   `oceandust_manual_page3.json`, and so on. As of writing there are 2 pages
   (422 total products).
4. Run:
   ```powershell
   py import_oceandust_manual.py
   ```
   This upserts OceanDust's products (scoped only to OceanDust - it never
   touches any other store's rows) and marks any previously-imported
   OceanDust product no longer present as inactive.
5. Delete the `oceandust_manual_page*.json` files afterward - they're just
   scratch input, not meant to be kept or committed.

### 3. Spot-check the results locally
Start the local dev server if it isn't already running:
```powershell
uvicorn api:app --reload
```
Then open `http://127.0.0.1:8000` and:
- Open the "Game Collections" dropdown and skim for anything that looks
  obviously wrong (duplicate entries for the same franchise, a generic word
  standing alone as its own "franchise", anything that looks like a raw
  scraped tag rather than a clean name).
- Spot-check 2-3 product cards on the homepage to confirm images/prices look
  right.
- If anything looks off, it's much cheaper to catch and fix it now (locally)
  than after it's live. See the "Fixing a bad franchise tag" section below.

### 4. Push the database live
```powershell
.\sync_to_cloud.ps1 -SkipScrape
```
(`-SkipScrape` reuses the database you already scraped and checked in steps
1-3, rather than scraping a second time.) You'll be prompted for your SSH key
passphrase. No service restart is needed for a database-only push (uvicorn
opens a fresh SQLite connection per request), **unless** you also changed any
`.py`/`.html`/CSS files this session, in which case follow the "Deploying
code changes" section below first.

If you'd rather push manually instead of using the script, the equivalent
command is (substitute your actual VPS IP - kept locally only, never
committed to this repo):
```powershell
scp apparel_aggregator.db ubuntu@<VPS_IP>:/opt/aggregate_apparel/apparel_aggregator.db
```

### 5. Verify it's live
Open `https://gamingapparel.gg` and confirm the product count / recent
additions match what you saw locally in step 3.

---

## Monthly routine (extra QA pass)

Once a month, do a slower, more thorough pass instead of just a quick glance:

1. Open the Game Collections dropdown and read through the **entire A-Z
   list**, not just the first screen. Fragmentation issues (e.g. a franchise
   split across "X" and "X: Subtitle") tend to hide further down the
   alphabet where you're less likely to scroll during a quick check.
2. If you spot an issue, look for the *pattern*: is this ONE mistagged
   product, or is it a systemic mapping bug that will keep recurring on every
   future scrape? (This session found real examples of both kinds - see
   "Fixing a bad franchise tag" below.)
3. Check Google Search Console (search.google.com/search-console) for the
   `gamingapparel.gg` property:
   - **Sitemaps** page: confirm the last sitemap submission still shows
     "Success" with a healthy page count.
   - **Pages** report (under Indexing): see how many submitted URLs are
     actually indexed vs. excluded, and why.

---

## As-needed: deploying code changes

Only needed when `.py`, `.html`, or CSS files changed (not for routine
database-only pushes). The production server only actually needs:
`api.py`, `database.py`, `models.py`, `templates/`, `static/` - it never runs
`scraper.py`/`parsers/`/`franchise_discovery.py` itself (those are local-only
tools), but it's good practice to keep the whole codebase in sync anyway.

1. If any Tailwind classes changed in templates, rebuild CSS first:
   ```powershell
   npm run build:css
   ```
2. Run the test suite as a safety check:
   ```powershell
   py -m pytest tests/ -q
   ```
3. Push whichever files changed, for example (substitute your actual VPS IP):
   ```powershell
   scp api.py database.py models.py ubuntu@<VPS_IP>:/opt/aggregate_apparel/
   scp templates/index.html templates/base.html ubuntu@<VPS_IP>:/opt/aggregate_apparel/templates/
   scp static/css/tailwind.css ubuntu@<VPS_IP>:/opt/aggregate_apparel/static/css/tailwind.css
   ```
4. Restart the service so the new code takes effect:
   ```powershell
   ssh ubuntu@<VPS_IP> "sudo systemctl restart aggregate-apparel && sudo systemctl status aggregate-apparel --no-pager -l"
   ```
   Confirm the status output shows `Active: active (running)` with no errors.
5. Verify live at `https://gamingapparel.gg`.

---

## Fixing a bad franchise tag

If you spot a fragmented or mistagged franchise (e.g. "DOOM" and "DOOM
Eternal" showing as separate entries when they should be one), the fix
usually has two parts:

1. **Add or correct a mapping** in the `franchise_mappings` database table
   so future scrapes resolve it correctly (see `parsers/franchise_map.py`'s
   `clean_franchise_tag()` for how this table is used). Double-check any
   INSERT you write maps the keyword to the *correct* target name, not to
   itself - this exact mistake happened twice this session and silently
   persisted a bad tag through several scrapes before being caught.
2. **Directly update the currently-affected rows** in the `products` table,
   since a mapping table change only affects *future* scrapes, not what's
   already stored. A one-off Python script using `sqlite3` is the fastest way
   to do this (query, decide the fix, `UPDATE`, verify, then delete the temp
   script).

If a product genuinely doesn't belong on the site at all (wrong category,
non-gaming content, a "mystery bundle" grab-bag item with no real franchise),
delete that row instead of retagging it, and fix the root cause in the
relevant parser so it doesn't come back on the next scrape.

If you're not sure how to diagnose or fix something you find, just describe
what you're seeing (a screenshot of the dropdown or product page is enough)
in a chat with the AI and it can investigate and fix it the same way it did
in this session.

---

## Adding more franchise SEO content

`seed_franchise_content.py` seeds the curated intro write-ups shown on
`/franchises/{slug}` pages (the "About [Franchise]" box). It's idempotent, so
re-running it is always safe.

To add a new franchise write-up:

1. Add a new `(name, text)` tuple to the `drafts` list in
   `seed_franchise_content.py`, following the same style as the existing
   entries (no "official"/"licensed" framing, no em dashes).
2. Run the script to write it into your local database:
   ```powershell
   py seed_franchise_content.py
3. Review it locally at http://127.0.0.1:8000/franchises/{slug} (with
    uvicorn api:app --reload running) to confirm it reads well and renders
    correctly.
4. Push the updated database to production:
    scp apparel_aggregator.db ubuntu@<VPS_IP>:/opt/aggregate_apparel/apparel_aggregator.db 

---

## Where things live

- **Local machine**: all scraping/discovery compute happens here
  (`scraper.py`, `franchise_discovery.py`, `parsers/`). This is intentional -
  keeps paid cloud compute costs down.
- **Production VPS** (IP kept in your local PowerShell profile only - see
  below - path `/opt/aggregate_apparel/`): read-only FastAPI app (`api.py`)
  serving whatever database you last pushed. `ENABLE_SCRAPER_SCHEDULER=false`
  is set permanently there - do not change this, it's what keeps the scraper
  from ever running on the cloud instance.
- **`sync_to_cloud.ps1`**: an existing helper script that can run the scraper
  and push the database in one command. It reads its connection details
  (VPS IP, user, SSH key path, remote path) from environment variables -
  set `$env:CLOUD_SSH_HOST` (and optionally `$env:CLOUD_SSH_USER`,
  `$env:CLOUD_SSH_KEY`, `$env:CLOUD_REMOTE_PATH`) once in your PowerShell
  profile so the real VPS IP never has to live in this repo. Once set,
  running `.\sync_to_cloud.ps1` (from `Aggregate_Apparel_Tool`) works with no
  further setup - you'll just be prompted for your SSH key passphrase. Use
  `.\sync_to_cloud.ps1 -SkipScrape` to only push the existing local database
  without re-scraping first. It only handles the database, not
  template/code/CSS files - those still need manual `scp` per the "Deploying
  code changes" section.
