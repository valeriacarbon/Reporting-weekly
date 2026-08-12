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

## What this draft does NOT do yet

- **No live Metricool pull.** This draft uses one week's numbers transcribed
  from the PDF you shared, so we could nail the visual design first. Wiring
  `scripts/build_report.py` up to pull directly from Metricool (there's a
  Metricool MCP/API available) so it runs unattended every Friday is the
  natural next step, once you've signed off on the look.
- **GBP specials are still a manual number** — same as your current report,
  since Metricool doesn't expose Google Business specials counts.
- A couple of the smaller per-property numbers (posts/engagement, not
  followers/views) were transcribed from a compressed PDF screenshot and
  should be spot-checked against Metricool directly before this goes to
  anyone outside the team — the header/footer note on the page says so too.

## Hosting on GitHub Pages

`index.html` lives at the repo root so GitHub Pages can serve it with no
build step. To make it live at a public URL, one manual step is needed in
GitHub's repo settings (the automation account this session runs under
doesn't have access to toggle repo settings): **Settings → Pages → Source →
Deploy from a branch → pick this branch (or `main`, once merged) → `/ (root)`.**
After that, the URL will be `https://valeriacarbon.github.io/reporting-weekly/`.
