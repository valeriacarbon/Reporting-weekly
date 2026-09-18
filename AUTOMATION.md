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
- `from` = **6** days before that — use `<that-date>T00:00:00-06:00`
- `week_label` still shows both Thursdays (e.g. `"Aug 27 – Sep 3, 2026"`)
  for continuity with every previous week's label — only the underlying
  query/sum window is 6 days back, not 7.

Example: running Friday Sep 4, 2026 → `from = 2026-08-28T00:00:00-06:00`,
`to = 2026-09-03T23:59:59-06:00`, week_label = `"Aug 27 – Sep 3, 2026"`
(the label's start date, Aug 27, is one calendar day *before* `from` --
that's intentional, see below).

**Why 6, not 7 (fixed 2026-09-04):** the original formula used 7 days back
with both endpoints inclusive (`T00:00:00` on the start Thursday through
`T23:59:59` on the end Thursday), which is an 8-calendar-day span, not 7 --
and critically, it meant one week's `to`-Thursday and the next week's
`from`-Thursday were the *same calendar day*, so anything posted that day
got counted in both weeks' totals. Caught this on the Aug 27-Sep 3 run:
Metricool's GBP evolution connector showed stray `postsCount=1` readings
that traced back to posts already counted in the *previous* week's file.
Using 6 days back instead makes `from` land the day *after* the previous
week's `to`, closing the gap with zero overlap. Weeks before 2026-09-04
were not retroactively corrected -- the impact is at most one day's
activity inside a 7-8 day window, and isn't worth restating every past file
for.

**Cross-check GBP post counts against the real publishing calendar
(`getScheduledPosts`), not the posts analytics connector (`GMPO01`) and
not just the evolution SUM field.** Both analytics-side sources have
proven unreliable for dates, in *opposite* directions:

- The evolution connector's `postsCount` (GMEV17) has shown a systematic
  **+1-day** mislabeling -- e.g. a real post created Aug 24 showed up as
  `postsCount=1` on Aug 25 in the evolution rows.
- The individual posts connector (`GMPO01`/`GMPO10`/`GMPO11`) has shown
  the **opposite, a -1-day** mislabeling -- confirmed 2026-09-12: 12 of 13
  GBP properties published a real post on Sep 4 (verified against
  `getScheduledPosts`' ground-truth local `publicationDate` + `status`),
  but `GMPO01` labeled every one of them Sep 3. Trusting `GMPO01` alone
  under-reported that week's real Posts Published as 0-2 instead of 12.

**The fix: use `getScheduledPosts(brandId, fromDate, toDate, timezone,
extendedRange=true)` as the source of truth for GBP posts_published**,
not either analytics connector. Call it per property using that
property's own `timezone` from `getBrandSettings` (do not reuse one
timezone across properties -- they're spread across America/New_York,
America/Chicago, and America/Mexico_City), with `fromDate`/`toDate`
spanning a day before/after the week window in that local timezone. Count
only entries whose `providers` array contains `{"network": "gmb", ...}`
with a `status`/`detailedStatus` of `PUBLISHED`, and whose local-timezone
`publicationDate` calendar date falls inside `[from_date, to_date]`. A
`PENDING` GBP entry (scheduled but not yet fired) does not count as
published yet, even if its date is inside the window. Despite its own
tool description saying it "only retrieves posts that are scheduled (not
yet published)", it has empirically returned already-`PUBLISHED` posts
too in this account -- trust the `status` field on each returned entry,
not the tool description.

Only fall back to the two analytics connectors (cross-checking each
other) if `getScheduledPosts` comes back empty for a property that should
have posted -- that's more likely a real API hiccup than a labeling bug.

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
| googleBusinessProfile | `["GMEV17","GMEV16","GMEV18","GMEV19","GMEV21","GMEV22","GMEV23"]` | posts published(SUM), post views(SUM), reachSearch(SUM), reachMaps(SUM), websiteClicks(SUM), callClicks(SUM), directionsClicks(SUM) |

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
kpis.followers / posts / views = sum across all 15 properties' respective
  values (each with a delta per Step 5)

kpis.engagement = sum across all 15 properties' engagement values, PLUS
  Google Business action clicks (website_clicks + phone_clicks +
  directions_clicks, this week's totals from google_business below) —
  added 2026-09-12 per Val's request, since GBP has no likes/comments/
  shares to fold in the way FB/IG/TikTok do, and clicks are the closest
  equivalent. Compute the delta the normal way, straight against the
  previous file's kpis.engagement.current — same as every other KPI,
  don't adjust or reconstruct that baseline. (A same-day fix on
  2026-09-12: an earlier version of this note had you recompute an
  "adjusted" previous-week baseline that added GBP clicks retroactively,
  to make the one-time methodology change look like a clean
  apples-to-apples comparison. That backfired — the adjusted number never
  appears anywhere on the dashboard, so the delta didn't match what Val
  actually saw published last week, and read as a drop when the real
  number had gone up. Just diff against what was actually shown; the one
  week this changed will have a delta that's partly the GBP-clicks
  addition and partly organic, and that's fine to leave as-is.)

engagement_by_channel = per network (Facebook/TikTok/Instagram/Google
  Business), matching kpis.engagement's composition: each social
  network's interactions sum, plus Google Business's total clicks (same
  number as above). No delta needed (same shape as posts_by_channel) —
  rendered as chips on the Engagement tile so the GBP contribution is
  visible, not folded in silently.

followers_by_channel = per network (Facebook/TikTok/Instagram — no GBP here,
  matches the existing report), sum of that network's followers across all
  properties that have it connected, with delta

posts_by_channel = per network (Facebook/TikTok/Instagram/Google Business),
  sum of that network's post count across all properties (no delta needed,
  matches existing shape)

facebook_groups = {groups_posted_in, groups_and_posts, interactions} always
  {0,0} with the existing note — Metricool doesn't expose Facebook Group
  data; only change this if that ever becomes available. "interactions" is
  likes+comments+shares combined into one manually-entered number (not
  tracked separately). "groups_and_posts" is {groups: {current, delta},
  posts: {current, delta}} — how many distinct groups had a post go out
  this week, and how many total posts across those groups (a group can get
  more than one post) — rendered as a single combined card, not two tiles.

google_business.posts_published    = sum of GBP posts_published across
  properties for the GBP_CURRENT window (see "GBP uses its own window"
  below), with delta vs GBP_PRIOR. Verify this against the real publishing
  calendar (`getScheduledPosts`), not the evolution connector's postsCount
  — see the cross-check section further up.
google_business.post_views         = sum of GBP postsViews (GMEV16) across
  properties for the GBP_CURRENT window, with delta vs GBP_PRIOR. This is
  the ONLY metric that measures how the GBP posts themselves performed
  (not the listing/profile overall) — see the "GBP posts vs. profile"
  note below before assuming Reach/Clicks have anything to do with
  posting activity.
google_business.reach_search       = sum of GMEV18 across properties for
  the GBP_CURRENT window, with delta vs GBP_PRIOR
google_business.reach_maps         = sum of GMEV19, same window/delta rule
google_business.website_clicks     = sum of GMEV21, same window/delta rule
google_business.phone_clicks       = sum of GMEV22, same window/delta rule
google_business.directions_clicks  = sum of GMEV23, same window/delta rule
```

`gbp_by_property` is a separate array (used by the "Google My Business —
by brand" per-property cards) with one entry per GBP-connected property
(everyone except Capri Palms and Aztec Villa, which aren't on GBP):
`{name, posts_published, post_views, reach_search, reach_maps,
website_clicks, phone_clicks, directions_clicks}` — no delta per field,
just the GBP_CURRENT window's raw numbers (the cards show magnitude bars,
not week-over-week chips). `posts_published` here should always match
that property's `posts_channels["Google Business"]` value in the
`properties` array **only when GBP_CURRENT happens to equal this run's
own week** — once GBP has its own window (the normal case), the two can
legitimately differ, since `properties[].posts_channels` stays on this
run's own Step 1 window while `gbp_by_property` follows GBP_CURRENT.

There is no `google_business.specials_posts` anymore — Metricool does track
Google Business posts after all (it was wrongly treated as a manual-only
metric for a couple of weeks); everything GBP now comes straight from the
API, no manual entry needed.

### GBP uses its own window, independent of the rest of the report (added 2026-09-19)

**Do not assume GBP data for this run's own Step 1 window (`from`/`to`) is
usable.** Verified 2026-09-19: even 8 days after the Sep 4-10 week ended,
a fresh pull of that week's `reachSearch` totaled only ~26% of what it
read a week later (1,544 vs 5,925 portfolio-wide) — Google's own
reporting can lag *materially* longer than the "same-day recheck" pattern
documented elsewhere in this file for other fields. Querying GBP on the
same Step 1 window as everything else will routinely under-report by
70-75% or more, silently.

**The fix: `google_business` and `gbp_by_property` use their own date
window, found by walking backward from the most recent completed week
until one passes a completeness check** — never hardcode a fixed lag (a
fixed N-day offset will eventually be wrong in one direction or the
other as Google's own pipeline speeds up or slows down).

**Algorithm:**
1. Start with `GBP_CURRENT` = this run's own Step 1 week (the most recently
   completed Friday-Thursday window).
2. **Completeness test** for a candidate week: pull `["GMEV18","GMEV19","GMEV21","GMEV22","GMEV23"]`
   (daily rows, not pre-aggregated) for every GBP-connected property over
   that candidate's 7 days. The candidate is **complete** only if every
   one of those properties has a **non-null `reachSearch` (GMEV18) value
   for every one of the 7 calendar days** in range. `reachSearch` is the
   signal to key on — it was the only one of the 5 fields that never
   showed a stray null even on data confirmed stable weeks later, while
   `reachMaps`/`websiteClicks`/`callClicks`/`directionsClicks` can
   legitimately stay null for a single low-traffic property/day
   indefinitely (a real sparse zero, not a sync gap) — requiring *all
   five* fields non-null means no week ever passes and the walk-back
   never terminates. A day with a row present but `reachSearch` null
   (e.g. a day that "returns Maps only") still fails the test.
3. If the candidate fails, step back one week (both `from` and `to` move
   back 7 days, keeping the same Step-1 boundary convention) and test
   again. Repeat until a candidate passes.
4. The first week that passes becomes **GBP_CURRENT**. Then test the week
   immediately before it the same way — since it's older, it will
   virtually always already pass — and that becomes **GBP_PRIOR**, the
   baseline for GBP delta comparisons. (Don't skip this second test; in
   principle a property could have a real historical gap.)
5. Compute `google_business` and `gbp_by_property` from GBP_CURRENT's raw
   pulled data (SUM per field, null treated as 0, same as every other GBP
   aggregation in this file). Compute deltas against GBP_PRIOR's
   equivalent totals (pull GBP_PRIOR fresh the same way — don't reuse a
   stale stored value from an old file, since by definition that old
   file's own GBP numbers were written before GBP_PRIOR had stabilized).
6. Write `gbp_window_label` and `gbp_prev_window_label` at the top level
   of the data file — the same label format as `week_label`/`prev_week_label`
   (label start = one calendar day before that window's `from`) — e.g.
   `"gbp_window_label": "Sep 3 – 10, 2026"`. `build_report.py` reads these
   to render a note box under the "Google My Business" heading explaining
   the window mismatch, and to relabel each GMB tile's delta chip (e.g.
   "vs Aug 27 – Sep 3, 2026" instead of "vs last wk").
7. `posts_published` is NOT subject to this lag — it's sourced from
   `getScheduledPosts` (the real publishing calendar), which is either
   published or not, with no gradual-backfill behavior. Still compute it
   for GBP_CURRENT/GBP_PRIOR (not this run's own week) so the six GMB
   tiles stay internally consistent about which window they describe —
   just don't bother re-verifying it against multiple candidate weeks the
   way Reach/Clicks needs.

### `posts_published` MUST use `scripts/gbp_window.py` — never re-derive the window ad hoc (fixed 2026-09-19)

**What went wrong:** the first implementation of the independent-window
feature above computed GBP_CURRENT/GBP_PRIOR for Reach/Clicks correctly,
but for `posts_published` it either reused an old, already-stale stored
value or re-derived the window boundaries separately for the
`getScheduledPosts` call. Because GBP posts publish Friday at 12:00
local — the first day of the window, and the day 100% of GBP posts land
on — any off-by-one in that second, independent derivation doesn't
degrade gracefully: it silently reassigns an entire week's post count to
the adjacent week, every time, with zero partial failures to notice. This
is exactly what happened to the Sep 10-17 run: GBP_CURRENT (Sep 4-10)
read 0 published posts and GBP_PRIOR (Aug 27-Sep 3) read 13, when the
true values (independently re-verified via exact, non-widened
`getScheduledPosts` pulls per brand-local timezone) are **12** and **1**.

**The fix is architectural, not a one-week number correction.**
`scripts/gbp_window.py` is now the single source of truth for GBP window
boundaries:

- `resolve_gbp_windows(current_start)` takes GBP_CURRENT's Friday (the
  date the walk-back completeness check in step 2 above lands on) and
  returns `current_start`/`current_end`/`prior_start`/`prior_end` as
  calendar `date` objects. **Call this once.** Use its output for both
  the `getAnalyticsDataByMetrics` `from`/`to` (via `to_query_range`) and
  the `getScheduledPosts` post-count filtering. Never derive the window a
  second time for one and not the other.
- `local_date_of(post["publicationDate"])` extracts the calendar date a
  post published on directly from Metricool's local `dateTime` string —
  no UTC conversion, no report-server timezone. Compare it against the
  window with `in_window(d, start, end)`, which is inclusive on both
  ends (the start Friday belongs to the current window, never the prior
  one).
- `is_published_gbp_post(post)` is the only correct provider check: a
  post counts for GBP iff one of its `providers` has `network == "gmb"`
  and `status == "PUBLISHED"`. A PENDING gmb provider never counts, even
  if another provider (e.g. Facebook) on the same post is PUBLISHED.
- `count_gbp_posts_by_property(posts_by_property, start, end)` returns
  the per-property counts to write into `gbp_by_property[].posts_published`
  — sum them to get the headline `google_business.posts_published.current`.
  The two must always match (`build_report.py` asserts this — see below).
- When writing the new data file, also write a top-level `gbp_window`
  object recording the exact dates used:
  ```json
  "gbp_window": {
    "current": {"start": "2026-09-04", "end": "2026-09-10"},
    "prior": {"start": "2026-08-28", "end": "2026-09-03"}
  }
  ```
  `build_report.py` re-derives the expected window from `gbp_window.current.start`
  via `resolve_gbp_windows` and calls `assert_matching_windows` against
  the stored dates on every build, printing both windows to the build log
  unconditionally and raising loudly (failing the build) on any
  divergence — plus cross-checking that `gbp_by_property` posts sum to
  the headline total. **Never skip writing `gbp_window`** — without it
  this guard is silently skipped (only true for weekly files that predate
  this feature).
- `scripts/test_gbp_window.py` has the regression suite for the exact
  boundary cases that caused this bug (Friday-noon-on-day-1,
  Thursday-23:59:59-on-last-day, Friday-00:00-the-day-after, the same
  Friday-noon post across America/New_York, America/Chicago and
  America/Mexico_City, a PENDING gmb post inside the window, and the
  per-property-sum-equals-headline check). Run it (`python3
  scripts/test_gbp_window.py`) any time this logic is touched.

**Everything else in this report is unaffected.** Followers, Posts,
Engagement, Views, the by-brand property detail, Facebook Groups, and
both GA4 URL Tracking sections all keep using this run's own Step 1
window exactly as before — GBP_CURRENT/GBP_PRIOR only ever apply to the
`google_business` and `gbp_by_property` blocks (Posts Published,
Reach · Search, Reach · Maps, Website Clicks, Phone Clicks, Directions
Clicks, and the by-brand GBP cards). Do not let `week_label`/
`prev_week_label` drift to match GBP_CURRENT — they describe the rest of
the report and must stay on this run's own window.

**In the common case GBP_CURRENT will be one full week behind this run's
own window** (i.e. equal to the *previous* run's window) — that's normal,
expected, and not a bug to "fix" by pulling harder. Only walk back
further than one week if that one-week-back candidate still fails the
completeness test.

The GMB section on the dashboard shows exactly 6 tiles, in this order:
Posts Published, Reach · Search, Reach · Maps, Website Clicks, Phone
Clicks, Directions Clicks — laid out 3 per row. The old combined
Reach/Clicks/Specials Posts tiles are gone.

**Post Views is temporarily hidden (as of 2026-08-28), not deleted.**
Keep computing and writing `google_business.post_views` and each
`gbp_by_property[].post_views` in the data file every week per the
formula below, but `build_report.py` no longer renders a tile for it,
and `gbp_property_card` no longer shows a Views row under Posts — see
"Post Views investigation" below for why. Don't remove the field from
the data schema; this is a display-only pause until that's resolved.

### GBP posts vs. the underlying business profile

Google Business Profile has two conceptually separate things going on, and
it's easy to mix them up:

- **Posts** — small content updates you publish directly to the listing
  (like a mini social post). **Post Views (GMEV16)** is the only number
  that measures how those specific posts performed. It's a genuine
  post-performance signal, same role as Engagement/Views for
  Facebook/Instagram/TikTok.
- **The profile/listing itself** — the free card Google shows in Search
  and Maps (photos, hours, star rating, buttons). **Reach Search, Reach
  Maps, Website Clicks, Phone Clicks, and Directions Clicks all measure
  this listing, not the posts.** Someone can see/click the listing in a
  week with zero posts published, and posting a lot doesn't directly move
  these numbers — they're driven by whether people search for the
  property or find it on Maps at all.

**All of these are organic, not paid.** Google Business Profile Insights
(what Metricool reads via GMEV*) only ever reports the free/organic
listing — there is no "GBP ads" product to conflate it with. Separately,
checked `getBrandSettings` across all 15 properties as of 2026-08:
**no property has a Google Ads account connected in Metricool at all**
(only Lakeside/Lakeview has a Facebook Ads account connected, which is
irrelevant to GBP and isn't pulled into any Facebook number here anyway,
since Step 3 only ever queries the `evolution` connector, not `ads`). So
even setting aside that GBP Insights is inherently organic-only, there's
currently no paid channel in the picture that could be inflating these
numbers.

### Post Views investigation (unresolved as of 2026-08-28)

Post Views (GMEV16) came back `0` for every GBP-connected property on
both the week-2026-08-20 and week-2026-08-27 pulls. Initially treated as
the same reporting lag as Reach/Clicks (see above), but on the
Aug 20-27 run that lag theory was ruled out:

- Reach/Clicks for that same week DID eventually sync to real nonzero
  numbers on a same-day re-pull -- proving lag was real for those fields.
- Post Views stayed null/0 even after that re-pull, and even querying
  2 months back on the `evolution` connector (GMEV16) for a property
  with confirmed real posts.
- Went to the individual-post level (`posts` connector: GMPO01 date,
  GMPO12 `views`, GMPO13 `viewsCount`) for every post at every one of
  the 13 GBP properties, including posts a full week old with plenty of
  time to accumulate views -- every single one came back `null` (not
  `0` -- genuinely absent), for both fields, with no exceptions.

Val says Metricool's own reports (the ones she views/exports directly)
do show a views number for GBP posts, so the data likely exists in
Metricool somewhere -- just not under `GMEV16`/`GMPO12`/`GMPO13` via
`getAnalyticsDataByMetrics`, or not under a metric labeled "views" at
all (possibly she's seeing Reach relabeled, or a report screen this
tool doesn't have a field ID for). **Before re-attempting**: get a
screenshot or export of the exact Metricool report she's reading it
from, so the metric name shown there can be matched against
`getAnalyticsAvailableMetrics` output rather than guessing field IDs
again. Until that's resolved, the dashboard doesn't display Post Views
at all (see above) rather than showing a misleading 0.

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
- Do not mix networks in a single `getAnalyticsDataByMetrics` call.
- Do not treat the daily time-series rows as already-aggregated — always
  sum/pick-last yourself per Step 3.

## URL Tracking (manual for now)

A "URL Tracking" section (portfolio totals + a per-property card grid, both
below the Facebook Groups section) shows Views / Sessions / Engaged Sessions
/ Tours from Google Analytics for the `fbgroups / organic` session source —
i.e. traffic that came from links shared in Facebook Groups. It lives in
`data/week-*.json` under `url_tracking` (`views`/`sessions`/
`engaged_sessions`/`tours` at the top, plus `by_property`).

This is **not pullable from Metricool** — it comes from a GA4 report Val
exports/shares each week. As of the week-2026-08-20 file it was filled in
by hand from a PDF. Val mentioned wiring this to a Google Drive folder next,
so a future run may be able to fetch it directly — check whether a Drive
folder has been shared before defaulting to "ask a human for this week's
numbers."

There is a second, near-identical section, `gmb_url_tracking` (added
2026-09-08), showing the same shape of GA4 data but for traffic sourced
from the property's Google Business Profile (GA4 source `GMB / GMB`)
instead of Facebook Group links. Same manual-PDF situation, same "not
pullable from Metricool" caveat.

**If you don't have this week's GA4 numbers for either section, carry
forward last week's numbers unchanged (delta 0) rather than omitting the
key entirely.** (Fixed 2026-09-11 — a run had left both keys out of that
week's file when no new export had arrived, which made the whole card
structure vanish from the dashboard for a week; Val had never asked for
that and had to notice and flag it herself. Don't guess a *new* number,
but don't make an existing section disappear either — copy the previous
file's `views`/`sessions`/`engaged_sessions`/`tours`(or `key_events`) and
`by_property` verbatim, zero out the deltas, and update the section's
`note` to say plainly that no new export was received this week and the
numbers shown are carried forward unchanged.)

## Quarterly Report (`quarterly.html`) — separate, manual-only, do NOT touch here

There is a second page, `quarterly.html`, linked from a nav tab in the
header of both pages. It reuses the weekly report's visual system
(`scripts/template_quarterly.html`, same CSS/colors as `template.html`) but
shows **quarter totals with no delta/comparison** — built by
`scripts/build_quarterly_report.py` from a `data/quarterly-<label>.json`
file (e.g. `data/quarterly-2026-jun-aug.json`, covering Jun 1 – Aug 31,
2026).

**This page is explicitly NOT part of the Friday weekly automation.** Val
asked for it to stay static between requests — do not regenerate or edit
`quarterly.html` (or its data file) as part of a routine weekly run. Only
touch it if a message explicitly asks for the quarterly report to be
rebuilt or extended to a new period.

If you ever are asked to rebuild it: pull fresh from Metricool directly for
the full requested date range (same field IDs/aggregation rules as Steps
3–4 above, followers = LAST in range, everything else = SUM in range) —
don't try to assemble it from the weekly `data/week-*.json` snapshots, since
those don't cover the whole history and weekly windows can overlap by a day
(see the Step 1 fix above). Check `getBrandSettings` for each property's
`joinDate`/`firstConnectionDate` and flag any property whose Metricool
connection started partway through the requested period — their totals
will understate the true period since there's no data before that date.
Facebook Groups and URL Tracking are omitted from this page entirely (no
historical data to sum for the former; too few weeks of GA4 data for the
latter to represent a period total) — don't add placeholder zeros for
them, just leave those sections out like the current version does.
