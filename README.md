# Weekly Social Portfolio Dashboard

A visual, chart-based redesign of the weekly social report — replacing the
manual-paste "ledger" style report (`weekly-social-report-copy.html`) with a
dashboard: KPI tiles, ranked bar charts, and per-property small multiples.

## Why this design

- **Chart-based, not just numbers in cells.** Every section (followers by
  channel, posts by channel, views by property, per-brand detail) is a chart,
  not a table of pasted values.
- **Python-generated, not client-side canvas.** The previous automated report
  used canvas charts that render fine live but come out as empty boxes when
  printed/exported to PDF (you can see this in the reference PDF you shared —
  the "Followers by channel" and "Channel mix" boxes are blank). This version
  computes every bar's geometry in Python and renders it as plain inline
  SVG/HTML, so it looks identical live, printed, or exported — no JS charting
  library, nothing that can silently fail to paint.
- **Validated color system.** Channel colors (Facebook/TikTok/Instagram/Google
  Business) and the good/bad delta colors were run through the dataviz
  skill's CVD-safety validator for both light and dark mode, not eyeballed.
- **Dark by default, light mode available** via the toggle in the top right
  (matches the tone of your current report; a full report is legible either
  way).
- **Per-property posts trace back to a channel.** Each property card breaks
  its post count out by network (Facebook / Instagram / TikTok / GBP) instead
  of showing one aggregate number, so you can see at a glance where the
  week's activity actually happened.

## Structure

```
data/week-2026-08-06.json   this week's snapshot (transcribed from the PDF you shared)
scripts/template.html       the HTML/CSS shell with {{PLACEHOLDER}} slots
scripts/build_report.py     reads a data JSON, computes chart geometry, writes index.html
index.html                  the generated dashboard — this is what GitHub Pages serves
```

## Updating it week to week (current, manual first draft)

1. Copy `data/week-2026-08-06.json` to a new dated file, fill in the new
   week's numbers.
2. Run:
   ```
   python3 scripts/build_report.py data/week-YYYY-MM-DD.json
   ```
3. Commit and push `index.html` (and the new data file).

## Where the numbers come from right now

This draft mixes two sources, and the footer/generated-note on the page always
says which:

- **Followers, engagement, views, and the portfolio-level KPIs/channel
  totals** are transcribed from the Metricool-exported PDF you shared. The
  followers and views figures reconcile exactly against that PDF's own
  totals; engagement was close enough to trust for a first draft.
- **Per-property post counts and their channel breakdown** were pulled live
  from the Metricool API (`getAnalyticsDataByMetrics`, one call per
  network/property, counting posts + Reels + Stories) while building this
  draft — the PDF's small print turned out to have misread several
  properties' post counts (e.g. it showed The Benton at 4 posts; the live
  data says 3, all Facebook Stories, zero that week on TikTok). That live
  pull totals 34 posts across the portfolio, close to but not exactly
  matching the PDF's reported 37 — the ~3-post gap is most likely posts
  right at the week's UTC/local-timezone boundary, since the query window
  used a flat UTC day range rather than each property's own timezone.

**Next step for full accuracy:** wire `scripts/build_report.py` to call
Metricool directly (brand IDs and field IDs are already documented below)
using each property's own timezone for the week boundary, for every metric —
not just posts — so this runs unattended every Friday instead of starting
from a PDF.

- **GBP specials are still a manual number** — same as your current report,
  since Metricool doesn't expose Google Business specials counts.

### Metricool reference (for wiring up full automation)

- Brand IDs: call `getBrandSettings` — returns each property's Metricool
  `id` plus its connected network handles.
- Post-count field IDs (one call per network, per property, per week):
  `FBPO01` (Facebook posts), `FBST01` (Facebook Stories), `IGPO01` (Instagram
  posts), `IGRE01` (Instagram Reels), `IGST01` (Instagram Stories), `TKPO01`
  (TikTok videos), `GMPO01` (Google Business posts). Each returns one row per
  published item with its date — count rows in range, don't expect a
  pre-aggregated total.

## Hosting on GitHub Pages

`index.html` lives at the repo root so GitHub Pages can serve it with no
build step. To make it live at a public URL, one manual step is needed in
GitHub's repo settings (the automation account this session runs under
doesn't have access to toggle repo settings): **Settings → Pages → Source →
Deploy from a branch → pick this branch (or `main`, once merged) → `/ (root)`.**
After that, the URL will be `https://valeriacarbon.github.io/reporting-weekly/`.
