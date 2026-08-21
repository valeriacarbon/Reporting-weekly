# Weekly Automation Runbook

**This document is written for whatever agent/automation runs the Friday
7:00am (America/Mexico_City / Guadalajara, fixed UTC-6, no DST) weekly
update.** It replaces the old process of manually pasting Metricool numbers
into `weekly-social-report-copy.html` — **that file is deprecated, do not use
it anymore.** Everything below is self-contained; follow it in order.

## What this run does, in one sentence

Pull this week's real stats from Metricool for all 15 properties, roll last
run's "this week" numbers into "last week", write a new dated data file,
regenerate `index.html`, and push straight to `main` — no approval step,
this is meant to run fully unattended.

## Repository

`https://github.com/valeriacarbon/Reporting-weekly`, branch `main`.

- `data/week-YYYY-MM-DD.json` — one snapshot per week. Name the new file for
  the week's **end** date (the Thursday that just completed).
- `scripts/build_report.py` — reads a data file, writes `index.html`.
- `index.html` — generated output, served by GitHub Pages. Never hand-edit
  it; always regenerate it from a data file.

## Step 1 — Compute the week window

The report always covers **Thursday to Thursday**, ending the Thursday
immediately before the Friday this runs, in **America/Mexico_City (UTC-6,
fixed, no DST)**:

- `to` = yesterday (Thursday) — use `<that-date>T23:59:59-06:00`
- `from` = 7 days before that (the previous Thursday) — use
  `<that-date>T00:00:00-06:00`

Example: running Friday Aug 14, 2026 → `from = 2026-08-06T00:00:00-06:00`,
`to = 2026-08-13T23:59:59-06:00`, week_label = `"Aug 6 – 13, 2026"`.

(Properties themselves sit in Eastern/Central/Mexico City time, not all
UTC-6 — this can miscount a post right at the week's edge by a day. That's a
known, already-accepted limitation; do not try to fix it per-property, it
adds a lot of complexity for a small edge effect.)

## Step 2 — Brand IDs (Metricool)

Call `getBrandSettings` to confirm/refresh this table if unsure (e.g. a new
property was added). As of 2026-08, the mapping is:

| Property (as shown on the dashboard) | Metricool brandId | Connected networks |
|---|---|---|
| Lakeside/Lakeview | 5481589 | Facebook, Instagram, TikTok, GBP |
| The Benton | 5481650 | Facebook, Instagram, TikTok, GBP |
| The Lamar Lofts | 5481662 | Facebook, Instagram, TikTok, GBP |
| The Landings at North Ingleside | 6111464 | Facebook, Instagram, TikTok, GBP |
| The Kenzie | 6150098 | Facebook, Instagram, TikTok, GBP |
| Westminster Club | 6201865 | Facebook, Instagram, TikTok, GBP |
| Claxton Pointe & Pecan Ridge | 6201875 | Facebook, Instagram, TikTok, GBP |
| Berry Falls | 6201887 | Facebook, Instagram, TikTok, GBP |
| Ingleside Terrace | 6449298 | Facebook, Instagram, TikTok, GBP |
| Hills at Hoover | 6515604 | Facebook, Instagram, TikTok, GBP |
| Residences at the Overlook | 6564064 | Facebook, Instagram, TikTok, GBP |
| Santa Fe | 6564321 | Facebook, Instagram, TikTok, GBP |
| Villa Siena | 6564332 | Facebook, Instagram, TikTok, GBP |
| Aztec Villa | 6564812 | Facebook only |
| Capri Palms | 6587008 | TikTok only |

Only call the networks each property actually has connected.

## Step 3 — Pull metrics (one call per property per connected network)

Use `getAnalyticsDataByMetrics(brandId, from, to, metrics)`. **Combine
multiple field IDs from the same network in one call — but never mix
different networks in one call, it silently returns empty rows.** Use the
`evolution` connector fields below (already the SUM/LAST-friendly aggregate
fields, not per-post enumeration):

| Network | metrics to request | Meaning |
|---|---|---|
| facebook | `["FBEV17","FBEV33","FBEV35","FBEV34","FBEV12","FBEV22"]` | followers(LAST), posts(SUM), stories(SUM), interactions(SUM), post views(SUM), reel views(SUM) |
| instagram | `["IGEV01","IGEV37","IGEV16","IGEV38","IGEV05"]` | followers(LAST), posts(SUM), stories(SUM), interactions(SUM), views(SUM) |
| tiktok | `["TKEV07","TKEV01","TKEV06","TKEV02"]` | followers(LAST), videos(SUM), interactions(SUM), views(SUM) |
| googleBusinessProfile | `["GMEV17","GMEV18","GMEV19","GMEV21","GMEV22","GMEV23"]` | posts published(SUM), reachSearch(SUM), reachMaps(SUM), websiteClicks(SUM), callClicks(SUM), directionsClicks(SUM) |

**Do not use GMEV20 (reachTotal) or GMEV24 (totalClicks)** — those combined/formula
fields return no data for this account even though their component fields
(GMEV18/19 and GMEV21/22/23) do. Sum the components yourself: `reach = GMEV18 +
GMEV19`, `clicks = GMEV21 + GMEV22 + GMEV23`.

**The response is a daily time series**, e.g.
`{"rows":[["24.0",null,null,null,"20260803"], ...]}` — one row per day, last
column is the date `YYYYMMDD`. It is NOT pre-aggregated. For each field:
- If it's a **SUM** metric: add up the value across every row in range,
  treating `null` as 0.
- If it's a **LAST** metric (the two `followers` / `fbFollowers` fields):
  take the value from the row with the latest date that has a non-null
  value (skip trailing nulls if the last day or two haven't synced yet).

**The API can return rows dated up to one day past your requested `to`**
(confirmed on GBP's postsCount field — a query ending `2026-08-13` came back
with a row dated `2026-08-14`). Changing the UTC offset on `from`/`to` does
NOT fix this; the extra row comes back identically either way. Before
summing, explicitly discard any row whose date falls outside
`[from_date, to_date]` inclusive — do not trust the API to have already
bounded it. This bug inflated one week's GBP Posts Published from the
correct 9 up to 13 before it was caught; assume it can happen on any field,
not just GBP.

## Step 4 — Aggregate per property

For each property, using only the networks it has connected:

```
followers        = FB.fbFollowers + IG.followers + TikTok.followers
posts_channels   = { "Facebook": FB.postsCount + FB.storiesCount,
                      "Instagram": IG.postsCount + IG.stories,
                      "TikTok": TikTok.videos,
                      "Google Business": GBP.postsCount }
posts            = sum of posts_channels values present for that property
engagement       = FB.postsInteractions + IG.postsInteractions + TikTok.interactions
views             = FB.postsImpressions + FB.reelsVideoViews + IG.views + TikTok.views
top_channel      = whichever of Facebook/Instagram/TikTok has the highest
                    `views` contribution this week (tie → keep last week's
                    top_channel unchanged)
```

(GBP is never folded into `followers`/`engagement`/`views` — same as the
original report's design, where Google Business is its own separate section.)

## Step 5 — Roll forward and compute deltas

Find the most recently dated file in `data/` (by filename). **Its "current"
numbers become this run's "previous" baseline — do not re-fetch last week
from Metricool, just carry the old file's numbers forward.**

```
new_delta = new_current - old_current   (old_current from the previous file)
```

Apply this for every `{current, delta}` pair: portfolio KPIs,
`followers_by_channel`, per-property `followers`/`engagement`/`views`. The
per-property `posts` row does not carry a delta chip in the UI (channel
chips replace it) — just write `"posts": {"current": <value>}` with no
`delta` key, same shape as the existing data files.

## Step 6 — Portfolio-level aggregates

```
kpis.followers / posts / engagement / views = sum across all 15 properties'
  respective values (each with a delta per Step 5)

followers_by_channel = per network (Facebook/TikTok/Instagram — no GBP here,
  matches the existing report), sum of that network's followers across all
  properties that have it connected, with delta

posts_by_channel = per network (Facebook/TikTok/Instagram/Google Business),
  sum of that network's post count across all properties (no delta needed,
  matches existing shape)

facebook_groups = always {0,0,0} with the existing note — Metricool doesn't
  expose Facebook Group data; only change this if that ever becomes available

google_business.posts_published    = sum of GBP postsCount (GMEV17) across
  properties, with delta. This is posts PUBLISHED during the week window —
  not scheduled/future posts, despite the field's Metricool label.
google_business.reach_search       = sum of GMEV18 across properties, with delta
google_business.reach_maps         = sum of GMEV19 across properties, with delta
google_business.website_clicks     = sum of GMEV21 across properties, with delta
google_business.phone_clicks       = sum of GMEV22 across properties, with delta
google_business.directions_clicks  = sum of GMEV23 across properties, with delta
```

There is no `google_business.specials_posts` anymore — Metricool does track
Google Business posts after all (it was wrongly treated as a manual-only
metric for a couple of weeks); everything GBP now comes straight from the
API, no manual entry needed.

**GBP data can lag by several days** — a query run the morning right after
the week ends may come back with true zeros for reach/clicks (not null,
actual `"0.0"` values) simply because Google's own Business Profile
insights haven't synced into Metricool yet. If a run's GBP numbers all
come back suspiciously flat, say so in generated_note and don't treat it
as a real crash — but don't invent a delta-free "not available" placeholder
either; write the real (possibly zero) numbers you got, since the next
run will naturally correct itself once the data catches up.

The GMB section on the dashboard shows exactly 6 tiles, in this order:
Posts Published, Reach · Search, Reach · Maps, Website Clicks, Phone
Clicks, Directions Clicks — laid out 3 per row. Post Views and the old
combined Reach/Clicks/Specials Posts tiles are gone.

## Step 7 — Write the new data file

Create `data/week-<end-date>.json` (e.g. `data/week-2026-08-13.json`),
following the exact shape of `data/week-2026-08-06.json` (use it as the
structural template — same keys, same nesting). Set:

- `week_label`: e.g. `"Aug 6 – 13, 2026"`
- `prev_week_label`: the previous file's `week_label`
- `generated_note`: something like *"Pulled live from Metricool by the
  weekly automation on \<run date\>. All figures except Google Business
  Specials Posts are from the Metricool API for this exact week; Specials
  Posts defaults to 0 since Metricool doesn't track it — update it manually
  in this file and rerun `scripts/build_report.py` if you have the real
  count."*

## Step 8 — Build, commit, push

```
python3 scripts/build_report.py data/week-<end-date>.json
git add data/week-<end-date>.json index.html
git commit -m "Weekly update: <week_label>"
git push origin main
```

No PR, no approval step — push straight to `main` so GitHub Pages
(`https://valeriacarbon.github.io/Reporting-weekly/`) picks it up.

## Do NOT

- Do not touch or resurrect `weekly-social-report-copy.html` — it's
  deprecated, kept only for historical reference.
- Do not overwrite or delete older `data/week-*.json` files — each week gets
  its own file.
- Do not guess Google Business Specials Posts. Default to 0 with the note,
  never fabricate a number.
- Do not mix networks in a single `getAnalyticsDataByMetrics` call.
- Do not treat the daily time-series rows as already-aggregated — always
  sum/pick-last yourself per Step 3.
