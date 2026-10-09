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

**`getScheduledPosts` has a structural blind spot: posts published
directly through the Google Business Profile app/website, bypassing
Metricool's scheduler entirely, don't exist in its data at all** (fixed
2026-10-03, Ingleside Terrace, Sep 25-Oct 1 run). It only lists posts
Metricool itself scheduled -- there's no API-visible difference between
"this property posted nothing" and "this property posted directly to
Google," since both return nothing relevant from this tool. The
evolution connector's `GMEV17` (`postsCount`) *does* read Google's own
account activity regardless of origin, so a direct-to-Google post
should eventually show up there -- but only once it syncs, which given
the GBP lag documented below can take 1-2+ weeks, i.e. it will not be
available in time for the week it actually happened in. **There is no
automated way to catch this.** If a property's real activity doesn't
match what `getScheduledPosts` shows, ask Val rather than trusting the
tool silently -- she'll know if she posted outside Metricool. When she
confirms one, add it by hand to that property's
`posts_channels["Google Business"]` (and roll the total up through
`posts.current` / `posts_by_channel` / `kpis.posts`, same as any other
aggregate), and say so plainly in `generated_note` with enough detail
that a future run doesn't "helpfully" overwrite it back to 0. This is
scoped to `properties[].posts_channels` / `posts_by_channel` /
`kpis.posts` only (this run's own Step 1 window) -- it has nothing to do
with the separate `google_business` / `gbp_by_property` GBP_CURRENT
rollup, which runs on its own lagged window (see below) and wouldn't
even cover the same dates most weeks.

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
views_channels   = { "Facebook": FB.postsImpressions + FB.reelsVideoViews,
                      "Instagram": IG.views,
                      "TikTok": TikTok.views,
                      "Google Business": GBP.reachSearch + GBP.reachMaps }
                    (sparse — a channel the property doesn't have connected,
                    or whose value is 0, just isn't a key; see the GBP-views
                    note below for why Reach stands in for GBP "views")
views            = sum of views_channels values present for that property
top_channel      = whichever channel in views_channels (now INCLUDING Google
                    Business, added 2026-10-09 — see below) has the highest
                    value this week (tie → keep last week's top_channel
                    unchanged)
```

(`followers` and `engagement` still never fold in GBP — GBP has no
followers concept, and GBP's engagement-equivalent, GBP action clicks, is
added once at the portfolio `kpis.engagement` level, not per-property, see
Step 6. `views` is the one metric where GBP now DOES get folded in, both
per-property and portfolio-wide — the exception, not the rule.)

### GBP is now folded into Views, using Reach as the GBP proxy (added 2026-10-09, per Val)

**Why a proxy, not real GBP post views:** true per-post view data for GBP
(`GMEV16`, and the individual-post fields `GMPO12`/`GMPO13`) is confirmed
absent from this Metricool account — not a bug, re-verified live on
2026-10-09 (queried `GMEV16` alone, unaffected by the multi-field merge bug
elsewhere in this doc, still `0`/`null` for every real post) on top of the
original 2026-08-28 investigation (see "Post Views investigation" below).
That field is still not displayed anywhere on the dashboard, and still
shouldn't be — this is a separate decision.

**The GBP-views proxy is Reach: `GBP.reachSearch + GBP.reachMaps`** — i.e.
the same `google_business.reach_search` / `reach_maps` / `gbp_by_property[].
reach_search` / `reach_maps` figures already pulled and displayed in the
"Google My Business" section (see "GBP posts vs. profile" below for what
Reach actually measures — it's the *listing's* visibility, not the posts').
This is a deliberate substitution, same principle already used for
Engagement (GBP action clicks standing in for likes/comments, since GBP has
neither) — not a claim that Reach and post-views are the same thing, just
the closest real, reliable number Metricool gives us for "how many times
was this property seen on Google" when true post-view data doesn't exist.

- Uses the **same GBP_CURRENT window** as the rest of the GBP block (which
  may lag this run's own Step 1 week — see "GBP uses its own window"
  below), not this run's own window. This means `views` now mixes two
  different date ranges per property (FB/IG/TK for this run's week, GBP
  Reach for GBP_CURRENT) — same tradeoff Engagement already accepted.
- **`top_channel` MUST be recomputed over the full `views_channels` dict,
  including Google Business, every time `views_channels` changes** — not
  just Facebook/Instagram/TikTok. Missing this reintroduces exactly the bug
  Val caught in the first place (a channel badge that doesn't match what
  the stacked bar actually shows): on the first 2026-10-09 rebuild, 3
  properties in the Monthly file and 8 in the Weekly file had a stale
  `top_channel` that didn't match their new GBP-inclusive `views_channels`
  (e.g. Lakeside/Lakeview badged "TikTok" while Google Business was
  actually its largest views contributor) until this was caught and fixed.
- **This is a one-time methodology jump, same caveat as the 2026-09-12
  Engagement change**: any Views comparison (week-over-week, month-over-
  month) that spans before/after 2026-10-09 is not apples-to-apples. Diff
  straight against what was actually published, same as always — don't try
  to reconstruct an adjusted historical baseline (see the Engagement note
  above for why that backfires).

**This report is organic-only by design, not because no paid activity
exists (clarified by Val, 2026-10-09).** `IG.views` (IGEV05) can
technically include paid impressions if a Meta Ads account is connected
to the brand in Metricool, but Val deliberately does not connect Meta
Ads (or any ads account) into Metricool for properties that are actually
running paid campaigns in Ads Manager — this dashboard's scope is
organic social only, by her choice, not because paid activity isn't
happening. Don't conclude "no ads are running for this property" from
the absence of ads data here; the correct statement is "this report
doesn't include paid data, regardless of what's actually running in Ads
Manager." If asked whether a specific property's views include paid
reach, the honest answer is: Metricool has no ads account connected for
it, so nothing paid could be flowing into this number even if a real
campaign is live elsewhere — not an assurance that no campaign exists.

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

views_by_channel = per network (Facebook/Instagram/TikTok/Google Business),
  added 2026-09-25 to feed the by-channel stacked segments on the "This week
  vs last week" chart's current-week bar (see "This week vs last week" chart
  below). Facebook = postsImpressions + reelsVideoViews, Instagram = views,
  TikTok = views, same per-network fields Step 4's `views` formula sums.
  **Google Business = GBP.reachSearch + GBP.reachMaps (added 2026-10-09)** —
  no longer always 0; see "GBP is now folded into Views" above for why
  Reach is the GBP proxy here and not real post-view data (still absent/
  unreliable, see "Post Views investigation" below — that part hasn't
  changed). No delta needed, same shape as posts_by_channel/
  engagement_by_channel. **The four values must sum to exactly
  kpis.views.current** — build_report.py doesn't assert this one, so check
  it by hand before shipping. Write it every week now that the feature
  exists; an older file missing this key still renders (the chart falls back
  to one solid Views bar for that file only), but don't let that become the
  new normal.

properties[].views_channels = per-property channel breakdown of `views`,
  computed in Step 4 above (now includes Google Business = GBP Reach, added
  2026-10-09 — see "GBP is now folded into Views" above). Feeds
  `property_views_stacked_chart()` in `build_report.py` (see "Views by
  property is now a stacked bar chart" below). **Must sum to exactly that
  property's `views.current`** — not asserted in code, check by hand. Write
  it every week now that the feature exists, same as `views_by_channel`; a
  property missing this key falls back to a solid single-color bar for that
  property only, don't let that become the new normal either.

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

### "This week vs last week" chart: current-week bar stacked by channel (added 2026-09-25)

The "Portfolio at a glance" / "This week vs last week — portfolio totals"
log-scale chart (`wow_totals_chart()` in `scripts/build_report.py`) works the
same as before with one change: the **last week (gray) bar is still one
solid mark, unchanged** — but the **this week (blue) bar is now stacked by
channel** (TikTok/Instagram/Facebook/Google Business), so this week's
composition is visible without opening the per-channel sections further
down the page. The total value label on top of each bar, the bar's height/
position, and the log axis underneath are all computed exactly as before —
only the internal fill of the current-week bar changed.

- **`CHANNEL_ORDER`** (`scripts/build_report.py`) is the one fixed
  bottom-to-top stacking order used for every metric's stack, and the same
  order the small "by channel" legend lists — do not reorder it or make it
  vary per metric; the color-to-channel mapping (`CHANNEL_COLORS`, same
  `--ch-*` CSS vars used everywhere else in the report) has to stay
  identical across Followers/Posts/Engagement/Views and the rest of the
  dashboard, per Val's explicit ask.
- Each metric reads its breakdown from `followers_by_channel` /
  `posts_by_channel` / `engagement_by_channel` / `views_by_channel` (the last
  one is new — see Step 6 above for how to compute it). A channel absent
  from a given metric's breakdown (Google Business has no "Followers") is
  treated as zero and just doesn't get a segment — that's expected, not a
  bug.
- **The four (or three, for Followers) channel values for a metric must sum
  to exactly that metric's `kpis.*.current`** — the stack's top has to land
  on the same y-position as the existing total-value label above it, or the
  bar and its label visibly disagree. `build()` doesn't assert this
  automatically (unlike the GBP window guard); eyeball it or check by hand
  when writing a new data file.
- If a data file is missing one of these four `*_by_channel` keys entirely
  (only possible for `views_by_channel` right now, since it's the newest —
  the other three have existed for a while), that one metric's current-week
  bar falls back to the old solid single-color bar rather than rendering
  empty. Don't rely on that fallback going forward — write all four keys
  every week.
- Each segment (and the solid last-week bar) carries an SVG `<title>` for a
  native hover/focus tooltip naming the channel and its exact value — there's
  no client-side JS chart library in this report, so this is the accessible,
  zero-dependency way to expose the per-segment number without adding one.

### "Views by property" is now a vertical stacked bar chart, not a horizontal single-color ranking list (fixed 2026-10-09)

**What was wrong:** the old "Views by property" section (`property_bar_row`
in Weekly, `property_bar_row_total` in Quarterly/Monthly) was a horizontal
bar per property, colored by `top_channel` with a text badge naming that
channel. Val flagged (correctly) that this reads as if the **entire** bar
value belongs to the named channel — e.g. Residences at the Overlook showed
"12,676" next to an "INSTAGRAM" badge, which looks like 12,676 Instagram
views, when the real breakdown was Instagram 6,809 / TikTok 4,987 / Facebook
880 and Instagram was just this property's *largest* slice. Nothing was
wrong with the underlying number — the chart design was misleading about
its composition.

**The fix:** `property_views_stacked_chart()` in `scripts/build_report.py`
(shared by Weekly and Monthly — see below for Quarterly). Same visual
language as the "This week vs last week" chart above, rotated 90°: vertical
bars, one per property, each stacked by channel in `CHANNEL_ORDER`, log
scale for the same reason (one property can have 10x+ another's views).
Property name labels are rotated -45° under each bar since there can be 13+
properties. Needs `properties[].views_channels` per property (documented
under Step 6 above) — a property missing that key falls back to a solid
single-color bar (old behavior) rather than rendering empty, same
graceful-degradation pattern as `views_by_channel`'s fallback. **Don't rely
on that fallback** — write `views_channels` every run.

- The chart is drawn at a **fixed pixel width that grows with property
  count**, deliberately not `width="100%"` — with 13-15 properties, scaling
  down to fit a phone screen would make every bar and label unreadably
  small. The `.pstack-scroll` wrapper (`overflow-x: auto`) lets it scroll
  horizontally on narrow viewports instead, while desktop (wide enough to
  show it at native size) never needs to scroll.
- **Quarterly was NOT converted** — `property_bar_row_total` /
  `build_quarterly_report.py` still use the old horizontal single-color
  style. Converting it needs a `views_channels` breakdown per property for
  the quarter, which requires a fresh per-property FB/IG/TK pull from
  Metricool for that historical window (not derivable from what's already
  in `data/quarterly-*.json`) — do this the next time Quarterly is
  refreshed, not as a standalone task.
- Same per-segment `<title>` tooltip pattern as the wow chart (`{property}
  — {channel}: {value}`).

### GBP uses its own window, independent of the rest of the report (added 2026-09-19)

**THE RULE (per Val, confirmed 2026-10-09): GBP always syncs on the last
fully-completed week — never this run's own Step 1 week.** Don't try to
chase this run's own window for GBP; it will not be synced yet (Metricool
documents a standard 5-6 day lag), and that's expected, not a bug. The
walk-back/completeness-test mechanics below exist to *verify* this rule
and to catch the rare case where even last week isn't complete yet (or
to catch the query-merge bug — see the dedicated section further down) —
they are not there to discover some other, shorter-than-a-week answer.
If you ever find yourself concluding GBP_CURRENT should equal this run's
own week, stop and re-check: that would break the rule and is far more
likely a misread than a real exception.

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

### The "multi-week GBP lag" (2026-09 runs) was a false alarm — the real bug was in how the completeness test itself queries data (fixed 2026-10-08)

**What went wrong:** for three weekly runs in a row (Sep 11-17, Sep 18-24,
Sep 25-Oct 1), the walk-back completeness test above concluded every
candidate week back to Sep 4-10 was incomplete, so GBP_CURRENT got stuck
at Sep 4-10 for three weeks running. This was reported in each of those
runs' `generated_note` as a genuine multi-week Google/Metricool sync lag.
**It wasn't.** Val checked Metricool's own UI directly on 2026-10-08 and
saw September fully loaded, with only Metricool's standard "some GBP
metrics may not be available for the last 5-6 days" disclaimer — nothing
close to a 3+ week lag.

**Root cause:** `getAnalyticsDataByMetrics` called with all 5 GBP
evolution fields together (`["GMEV18","GMEV19","GMEV21","GMEV22","GMEV23"]`)
**intermittently drops entire dates from the merged result**, even though
every one of those dates has real, non-null data. Confirmed directly:
running the *exact same* 5-field call twice in a row, seconds apart, for
the same property and date range produced two different results — the
first cut off partway through the range (looking exactly like a sync
lag), the second returned the full range cleanly. Pulling each field
**individually** (`["GMEV18"]` alone, etc.) always returned the complete,
correct range, every time. The bug is specific to combining multiple
evolution fields in one call — it is not a real gap in Metricool's data,
and it is not a Google-side reporting lag.

**The completeness test (step 2 above) was unknowingly measuring this
bug, not real data completeness** — a candidate week "failed" because
the 5-field query dropped some of its dates in the merged response, not
because Google/Metricool hadn't synced that week yet.

**Fixed procedure — do this from now on:**
1. Still pull all 5 fields together first (one call per property, as
   before — it's usually fine and saves calls).
2. **Before concluding a date is missing, check row count first.** A
   genuinely complete week returns exactly 7 rows per property (one per
   calendar day — `reachSearch` can legitimately be `null` within a row,
   but the row itself must be present for all 7 dates). If any property
   returns fewer than 7 rows, **do not conclude the week is incomplete
   yet** — re-run the identical call once more. If the retry returns all
   7 rows, use that (the first call hit the merge bug). Only treat a week
   as genuinely incomplete if a property *still* comes back short after a
   retry.
3. If a retry still comes up short, fall back to pulling that property's
   missing fields individually or in pairs (e.g. `["GMEV18","GMEV19"]` then
   `["GMEV21","GMEV22","GMEV23"]`) rather than all 5 together — this has
   not been observed to drop dates in this account.
4. **Never conclude a multi-week lag from a single pull.** If a week looks
   incomplete, retry before walking back further — walking back without
   retrying is how the false 3-week "lag" got reported as fact three runs
   in a row.

**Correction applied 2026-10-08:** re-ran the completeness test with the
retry procedure above for Sep 25-Oct 1 (this run's own week) and Sep
18-24 (prior week) — both came back fully complete, all 13 properties,
13×7=91 rows exactly, no retries even needed. GBP_CURRENT/GBP_PRIOR are
corrected to Sep 25-Oct 1 / Sep 18-24 in `data/week-2026-10-01.json` (see
that file's `generated_note` for the exact before/after numbers). Earlier
weekly files (`data/week-2026-09-17.json`, `week-2026-09-24.json`) were
**not** retroactively corrected — their GBP numbers may have the same
issue, but those reports already shipped and this fix is going forward
only, per the file-naming/immutability convention elsewhere in this repo.

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

**`gmb_url_tracking`'s window must match the GBP window, not necessarily
the `url_tracking` (FB Groups) window** (fixed 2026-10-09, per Val: "pls
replace the data for this one, so we have both synced on the same week").
GBP follows the last-fully-completed-week rule (see above), which can be
a different window than whatever date range Val's latest GA4 export
happens to cover. If Val shares a GMB GA4 export for a window that
doesn't match the current file's `gbp_window_label`, don't just drop it
in — check which window it actually covers and use it for whichever
week (this one or last week's file) that window matches, so the GMB URL
Tracking numbers and the GBP reach/clicks numbers above them are always
describing the same week. `url_tracking` (FB Groups) has no such
constraint — it isn't paired with a GBP-windowed section, so it just
uses whatever window Val's latest FB Groups export covers.

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

## Monthly Report (`monthly.html`) — separate, manual-only, do NOT touch here

There is a third page, `monthly.html`, linked from the same nav tab bar as
the other two. Same pattern as the Quarterly Report, just a calendar-month
window instead of a quarter: `scripts/template_monthly.html` (same CSS as
`template.html`/`template_quarterly.html`), built by
`scripts/build_monthly_report.py` from a `data/monthly-<label>.json` file
(e.g. `data/monthly-2026-sep.json`, covering Sep 1 – Sep 30, 2026). It
reuses `total_tile`/`property_bar_row_total`/`property_card_total` from
`build_quarterly_report.py` rather than duplicating them.

**This page is explicitly NOT part of the Friday weekly automation.**
Only touch it if a message explicitly asks for the monthly report to be
rebuilt or extended to a new month.

If you ever are asked to rebuild it: pull fresh from Metricool directly for
the full requested calendar month (same field IDs/aggregation rules as
Steps 3–4 above, followers = LAST in range, everything else = SUM in
range) — don't assemble it from weekly `data/week-*.json` snapshots, same
reasoning as Quarterly. Check `getBrandSettings` joinDate/firstConnectionDate
for partial-month properties, same as Quarterly.

**Unlike Quarterly, this page DOES include `url_tracking` and
`gmb_url_tracking`** (added 2026-10-09, per Val) — she shared a full-month
GA4 "Organic Links Performance" export (`fbgroups / organic` and
`GMB / GMB` source/medium) covering the whole calendar month, which is
exactly the period-total shape this page needs. Same data shape, same
`url_tracking_card`/`gmb_url_tracking_card` components and `total_tile`
(no delta) as every other stat on this page — see `build_monthly_report.py`
and `template_monthly.html` for the two sections
("URL Tracking" / "URL Tracking — by brand" and "Google My Business — URL
Tracking" / "... by brand"). If a future month's rebuild doesn't come with
a matching GA4 export, leave these two keys out of that month's data file
entirely (don't invent zeros) and the sections will simply not render —
same graceful-omission behavior Quarterly still uses for these sections.

For `top_channel` (used for both the Views-by-property bar color and the
property card badge): it's the channel with the most **views** for that
property in the period, not the most posts — don't compute it from posts
counts, that was a bug caught and fixed during the first build
(2026-10-08).

**GBP reach/clicks (GMEV18/19/21/22/23) will look like they stop partway
through the month if you pull all 5 fields together in one call and take
the first result at face value — this is almost always the merge-drops-
dates bug, not a real sync gap.** Hit exactly this on the first Sep 2026
build (2026-10-08): a 5-field pull for Sep 1-30 came back with real data
through Sep 15 and nothing after, looking identical to a multi-week sync
lag. Re-running the *identical* call returned the full 30 days cleanly.
See the "multi-week GBP lag... was a false alarm" section above for the
root cause and the fixed retry procedure — it applies here exactly the
same way: check for 30 rows per property (not 7, since this is a
calendar month), and if any property comes up short, retry the identical
call before concluding anything is actually missing. Only report a
partial-month caveat if a property *still* comes up short after a retry.

**GBP posts published**: use `getScheduledPosts` ground truth (same as
the weekly report's cross-check), not the laggy `GMEV17` evolution field.
Remember the direct-to-GBP blind spot documented above — a property may
have posted straight through the Google Business Profile app, invisible
to `getScheduledPosts` entirely — so cross-check against anything Val has
already told you about a given month before trusting the tool's count as
complete.
