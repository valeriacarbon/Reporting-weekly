# Weekly Social Portfolio Dashboard

A visual, chart-based redesign of the weekly social report — replacing the
manual-paste "ledger" style report (`weekly-social-report-copy.html`, now
deprecated) with a dashboard: KPI tiles, ranked bar charts, and per-property
small multiples.

**Running the weekly update?** See [`AUTOMATION.md`](AUTOMATION.md) — it's
the complete, self-contained runbook (brand IDs, Metricool field IDs, week
math, JSON schema, commit/push steps) for whatever pulls this week's data
every Friday.

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

## Updating it week to week

The weekly Friday run follows `AUTOMATION.md` end to end (pull from
Metricool, roll last week forward, rebuild, push). For a one-off manual
edit, the mechanics are just:

1. Copy the most recent `data/week-*.json` to a new dated file, edit the
   numbers.
2. Run:
   ```
   python3 scripts/build_report.py data/week-YYYY-MM-DD.json
   ```
3. Commit and push `index.html` (and the new data file) to `main`.

## Where the numbers come from

As of the week-2026-08-06 file, the data was a hand-assembled mix (PDF
transcription + a first live Metricool pull) while the design was being
nailed down — see the git history on that file if you need the details.
**Every file from here on is meant to be pulled entirely live from
Metricool**, following `AUTOMATION.md` — no more PDF transcription, no more
manual paste-in, except the one number Metricool genuinely doesn't track
(Google Business Specials Posts, documented in `AUTOMATION.md`).

## Hosting on GitHub Pages

`index.html` lives at the repo root so GitHub Pages can serve it with no
build step. To make it live at a public URL, one manual step is needed in
GitHub's repo settings (the automation account this session runs under
doesn't have access to toggle repo settings): **Settings → Pages → Source →
Deploy from a branch → pick this branch (or `main`, once merged) → `/ (root)`.**
After that, the URL will be `https://valeriacarbon.github.io/reporting-weekly/`.
