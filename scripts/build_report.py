#!/usr/bin/env python3
"""
Builds the Weekly Social Portfolio dashboard (index.html) from a JSON data
snapshot. All chart geometry (bar widths, colors, delta chips) is computed
here in Python and rendered as inline SVG/HTML -- no client-side charting
library, no canvas. That means every chart is crisp, themeable, and renders
identically whether it's opened live, printed, or exported to PDF.

Usage:
    python3 scripts/build_report.py data/week-2026-08-06.json

To produce next week's report: drop a new dated JSON file in data/ (same
shape) and re-run this script with that file. It always writes to index.html
at the repo root, which is what GitHub Pages serves.
"""
import json
import sys
import html
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Validated categorical order (adjacent-pair CVD-safe in both light & dark --
# see the dataviz skill's palette validator). Direct labels are always shown
# alongside color, per the skill's relief rule for the borderline pairs.
CHANNEL_COLORS = {
    "Facebook":        {"dark": "#3987e5", "light": "#2a78d6"},
    "TikTok":          {"dark": "#199e70", "light": "#1baf7a"},
    "Google Business": {"dark": "#c98500", "light": "#eda100"},
    "Instagram":       {"dark": "#d55181", "light": "#e87ba4"},
}
SEQUENTIAL_BLUE = {"dark": "#3987e5", "light": "#2a78d6"}
STATUS_GOOD = {"dark": "#0ca30c", "light": "#006300"}
STATUS_BAD = {"dark": "#e66767", "light": "#e34948"}
STATUS_FLAT = {"dark": "#898781", "light": "#898781"}


def esc(s):
    return html.escape(str(s), quote=True)


def pct_delta(current, delta):
    prev = current - delta
    if prev == 0:
        return None
    return delta / prev * 100.0


def delta_chip(current, delta, is_new=False, suffix=""):
    """Renders a colored +/- chip with arrow, absolute delta, and % change."""
    if is_new:
        color_var = "var(--good)"
        return f'<span class="chip good">▲ new{esc(suffix)}</span>'
    if delta > 0:
        arrow, color_var, sign = "▲", "var(--good)", "+"
    elif delta < 0:
        arrow, color_var, sign = "▼", "var(--bad)", ""
    else:
        arrow, color_var, sign = "•", "var(--flat)", ""
    pct = pct_delta(current, delta)
    pct_txt = f" ({sign}{pct:.0f}%)" if pct is not None else ""
    return (f'<span class="chip" style="color:{color_var}">'
            f'{arrow} {sign}{delta:,}{pct_txt}{esc(suffix)}</span>')


def fmt(n):
    return f"{n:,}"


def mini_bar(current, max_value, css_var="series-sequential", height=6, width=64):
    """A tiny single-hue magnitude bar used inside stat tiles / property rows.
    css_var is a full CSS custom-property name (without the leading --), e.g.
    'series-sequential' or 'ch-facebook'."""
    max_value = max(max_value, 1)
    w = max(2, round((current / max_value) * width)) if current > 0 else 0
    color = f"var(--{css_var})"
    return (
        f'<svg class="minibar" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-hidden="true">'
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="{height/2}" '
        f'fill="var(--track)"/>'
        f'<rect x="0" y="0" width="{w}" height="{height}" rx="{height/2}" '
        f'fill="{color}"/></svg>'
    )


def channel_bar_row(channel, current, max_value, delta=None, unit=""):
    color_key = f"ch-{channel.lower().replace(' ', '-')}"
    max_value = max(max_value, 1)
    w_pct = (current / max_value) * 100
    delta_html = ""
    if delta is not None:
        delta_html = delta_chip(current, delta)
    return f'''
    <div class="chbar-row">
      <div class="chbar-label">{esc(channel)}</div>
      <div class="chbar-track">
        <div class="chbar-fill" style="width:{w_pct:.1f}%; background:var(--{color_key})"></div>
      </div>
      <div class="chbar-value">{fmt(current)}{esc(unit)} {delta_html}</div>
    </div>'''


def property_bar_row(name, current, max_value, delta, top_channel):
    color_key = f"ch-{top_channel.lower().replace(' ', '-')}"
    max_value = max(max_value, 1)
    w_pct = max(1.2, (current / max_value) * 100)
    return f'''
    <div class="pbar-row">
      <div class="pbar-label">{esc(name)}<span class="pbar-badge" style="color:var(--{color_key})">{esc(top_channel)}</span></div>
      <div class="pbar-track">
        <div class="pbar-fill" style="width:{w_pct:.1f}%; background:var(--{color_key})"></div>
      </div>
      <div class="pbar-value">{fmt(current)}</div>
      <div class="pbar-delta">{delta_chip(current, delta)}</div>
    </div>'''


def property_card(p, maxes):
    color_key = f"ch-{p['top_channel'].lower().replace(' ', '-')}"
    rows = []
    for key, label, unit in [
        ("followers", "Followers", ""),
        ("posts", "Posts", ""),
        ("engagement", "Engagement", ""),
        ("views", "Views", ""),
    ]:
        d = p[key]
        bar = mini_bar(d["current"], maxes[key], color_key, height=7, width=72)
        rows.append(f'''
        <div class="metric-row">
          <div class="metric-label">{label}</div>
          <div class="metric-bar">{bar}</div>
          <div class="metric-value">{fmt(d["current"])}</div>
          <div class="metric-delta">{delta_chip(d["current"], d["delta"])}</div>
        </div>''')
    return f'''
    <div class="property-card">
      <div class="property-card-head">
        <h3>{esc(p["name"])}</h3>
        <span class="top-channel-badge" style="border-color:var(--{color_key}); color:var(--{color_key})">{esc(p["top_channel"])}</span>
      </div>
      {"".join(rows)}
    </div>'''


def stat_tile(label, current, delta, is_new=False, prev_override=None):
    prev = prev_override if prev_override is not None else current - delta
    peak = max(current, prev, 1)
    bar = f'''
      <svg class="stat-spark" width="100%" height="18" viewBox="0 0 100 18" preserveAspectRatio="none" role="img" aria-hidden="true">
        <rect x="0" y="10" width="{(prev/peak)*100:.1f}" height="6" rx="3" fill="var(--track)"/>
        <rect x="0" y="0" width="{(current/peak)*100:.1f}" height="6" rx="3" fill="var(--series-sequential)"/>
      </svg>'''
    return f'''
    <div class="stat-tile">
      <div class="stat-label">{esc(label)}</div>
      <div class="stat-value">{fmt(current)}</div>
      <div class="stat-delta">{delta_chip(current, delta, is_new=is_new)}</div>
      {bar}
    </div>'''


def build(data_path: Path) -> str:
    data = json.loads(data_path.read_text())

    kpis = data["kpis"]
    kpi_html = "".join([
        stat_tile("Followers", kpis["followers"]["current"], kpis["followers"]["delta"]),
        stat_tile("Posts", kpis["posts"]["current"], kpis["posts"]["delta"]),
        stat_tile("Engagement", kpis["engagement"]["current"], kpis["engagement"]["delta"]),
        stat_tile("Views", kpis["views"]["current"], kpis["views"]["delta"]),
    ])

    fbc = data["followers_by_channel"]
    fbc_max = max(c["current"] for c in fbc)
    followers_chart = "".join(
        channel_bar_row(c["channel"], c["current"], fbc_max, c["delta"]) for c in fbc
    )

    pbc = data["posts_by_channel"]
    pbc_max = max(c["current"] for c in pbc)
    posts_chart = "".join(
        channel_bar_row(c["channel"], c["current"], pbc_max) for c in pbc
    )

    props = sorted(data["properties"], key=lambda p: p["views"]["current"], reverse=True)
    views_max = max(p["views"]["current"] for p in props)
    views_chart = "".join(
        property_bar_row(p["name"], p["views"]["current"], views_max, p["views"]["delta"], p["top_channel"])
        for p in props
    )

    maxes = {
        "followers": max(p["followers"]["current"] for p in props),
        "posts": max(p["posts"]["current"] for p in props),
        "engagement": max(p["engagement"]["current"] for p in props),
        "views": views_max,
    }
    property_cards = "".join(property_card(p, maxes) for p in props)

    fg = data["facebook_groups"]
    fg_html = "".join([
        stat_tile("Groups posted in", fg["groups_posted_in"]["current"], fg["groups_posted_in"]["delta"]),
        stat_tile("Group likes", fg["group_likes"]["current"], fg["group_likes"]["delta"]),
        stat_tile("Group comments", fg["group_comments"]["current"], fg["group_comments"]["delta"]),
    ])

    gmb = data["google_business"]
    gmb_html = "".join([
        stat_tile("Scheduled posts", gmb["scheduled_posts"]["current"], gmb["scheduled_posts"]["delta"], is_new=gmb["scheduled_posts"].get("is_new", False)),
        stat_tile("Specials posts", gmb["specials_posts"]["current"], gmb["specials_posts"]["delta"], is_new=gmb["specials_posts"].get("is_new", False)),
        stat_tile("Post views", gmb["post_views"]["current"], gmb["post_views"]["delta"]),
        stat_tile("Reach", gmb["reach"]["current"], gmb["reach"]["delta"]),
        stat_tile("Clicks", gmb["clicks"]["current"], gmb["clicks"]["delta"]),
    ])

    channel_css_vars = "\n".join(
        f'      --ch-{k.lower().replace(" ", "-")}: {v["dark"]};' for k, v in CHANNEL_COLORS.items()
    )
    channel_css_vars_light = "\n".join(
        f'      --ch-{k.lower().replace(" ", "-")}: {v["light"]};' for k, v in CHANNEL_COLORS.items()
    )

    template = (REPO_ROOT / "scripts" / "template.html").read_text()
    out = template
    out = out.replace("{{WEEK_LABEL}}", esc(data["week_label"]))
    out = out.replace("{{PREV_WEEK_LABEL}}", esc(data["prev_week_label"]))
    out = out.replace("{{GENERATED_NOTE}}", esc(data["generated_note"]))
    out = out.replace("{{KPI_TILES}}", kpi_html)
    out = out.replace("{{FOLLOWERS_CHART}}", followers_chart)
    out = out.replace("{{POSTS_CHART}}", posts_chart)
    out = out.replace("{{VIEWS_CHART}}", views_chart)
    out = out.replace("{{PROPERTY_CARDS}}", property_cards)
    out = out.replace("{{FB_GROUPS_TILES}}", fg_html)
    out = out.replace("{{FB_GROUPS_NOTE}}", esc(fg["note"]))
    out = out.replace("{{GMB_TILES}}", gmb_html)
    out = out.replace("{{CHANNEL_CSS_VARS_DARK}}", channel_css_vars)
    out = out.replace("{{CHANNEL_CSS_VARS_LIGHT}}", channel_css_vars_light)
    return out


def main():
    if len(sys.argv) != 2:
        print("usage: build_report.py data/week-YYYY-MM-DD.json", file=sys.stderr)
        sys.exit(1)
    data_path = Path(sys.argv[1])
    out = build(data_path)
    out_path = REPO_ROOT / "index.html"
    out_path.write_text(out)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
