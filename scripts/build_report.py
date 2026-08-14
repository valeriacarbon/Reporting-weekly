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
import math
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


def delta_chip(current, delta, is_new=False, suffix="", compare_label=""):
    """Renders a colored +/- chip with arrow, absolute delta, and % change.
    compare_label, if given, is folded inside the parens next to the percent
    (e.g. '+1% vs last wk') instead of appended after -- matches how the
    original report phrased its KPI tiles."""
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
    label = f" {esc(compare_label)}" if compare_label else ""
    pct_txt = f" ({sign}{pct:.0f}%{label})" if pct is not None else (f" ({esc(compare_label)})" if compare_label else "")
    return (f'<span class="chip" style="color:{color_var}">'
            f'{arrow} {sign}{delta:,}{pct_txt}{esc(suffix)}</span>')


def fmt(n):
    return f"{n:,}"


# Log-scale gridlines: each decade plus its half-decade (10, 50, 100, 500, ...),
# matching how widely followers/posts/engagement/views differ in magnitude.
LOG_GRIDLINES = [10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000]


def _log_domain(max_value):
    """Smallest gridline set spanning [10, next-power-of-ten above max_value]."""
    ceiling = 10
    while ceiling <= max_value:
        ceiling *= 10
    lines = [g for g in LOG_GRIDLINES if 10 <= g <= ceiling]
    return 10, ceiling, lines


def wow_totals_chart(kpis, week_label, prev_week_label):
    """Grouped bar chart (log scale) comparing this week vs last week across
    all four portfolio KPIs in one view -- they differ by orders of magnitude
    (posts in the tens, views in the tens of thousands), so a shared linear
    axis would flatten the smaller ones to invisible slivers. One hue, two
    shades (previous vs current), per the dumbbell/before-after form."""
    metrics = [
        ("Followers", kpis["followers"]),
        ("Posts", kpis["posts"]),
        ("Engagement", kpis["engagement"]),
        ("Views", kpis["views"]),
    ]
    values = []
    for _, k in metrics:
        values.append(max(k["current"], 1))
        values.append(max(k["current"] - k["delta"], 1))
    domain_min, domain_max, gridlines = _log_domain(max(values))

    W, H = 800, 300
    left_pad, right_pad, top_pad, bottom_pad = 64, 16, 16, 34
    plot_w = W - left_pad - right_pad
    plot_h = H - top_pad - bottom_pad
    log_min, log_max = math.log10(domain_min), math.log10(domain_max)

    def y_of(value):
        value = max(value, domain_min)
        frac = (math.log10(value) - log_min) / (log_max - log_min)
        return top_pad + plot_h * (1 - frac)

    group_w = plot_w / len(metrics)
    bar_w = min(46, group_w * 0.28)
    bar_gap = 6

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="auto" role="img" '
             f'aria-label="This week vs last week, all portfolio KPIs, log scale">']

    for g in gridlines:
        y = y_of(g)
        parts.append(f'<line x1="{left_pad}" y1="{y:.1f}" x2="{W - right_pad}" y2="{y:.1f}" '
                      f'stroke="var(--rule)" stroke-width="1"/>')
        parts.append(f'<text x="{left_pad - 8}" y="{y:.1f}" text-anchor="end" '
                      f'dominant-baseline="middle" class="wow-axis-label">{fmt(g)}</text>')

    for i, (label, k) in enumerate(metrics):
        current, prev = k["current"], k["current"] - k["delta"]
        cx = left_pad + group_w * i + group_w / 2
        prev_x = cx - bar_gap / 2 - bar_w
        curr_x = cx + bar_gap / 2
        prev_y, curr_y = y_of(prev), y_of(current)
        base_y = top_pad + plot_h
        parts.append(
            f'<rect x="{prev_x:.1f}" y="{prev_y:.1f}" width="{bar_w:.1f}" '
            f'height="{base_y - prev_y:.1f}" rx="4" fill="var(--compare-prev)"/>'
        )
        parts.append(
            f'<rect x="{curr_x:.1f}" y="{curr_y:.1f}" width="{bar_w:.1f}" '
            f'height="{base_y - curr_y:.1f}" rx="4" fill="var(--series-sequential)"/>'
        )
        parts.append(f'<text x="{prev_x + bar_w/2:.1f}" y="{prev_y - 8:.1f}" text-anchor="middle" '
                      f'class="wow-value-label">{fmt(prev)}</text>')
        parts.append(f'<text x="{curr_x + bar_w/2:.1f}" y="{curr_y - 8:.1f}" text-anchor="middle" '
                      f'class="wow-value-label">{fmt(current)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{base_y + 20:.1f}" text-anchor="middle" '
                      f'class="wow-cat-label">{esc(label)}</text>')

    parts.append(f'<line x1="{left_pad}" y1="{top_pad + plot_h:.1f}" x2="{W - right_pad}" '
                  f'y2="{top_pad + plot_h:.1f}" stroke="var(--baseline)" stroke-width="1.5"/>')
    parts.append("</svg>")

    legend = (
        '<div class="wow-legend">'
        f'<span class="legend-item"><span class="legend-dot" style="background:var(--compare-prev)"></span>{esc(prev_week_label)}</span>'
        f'<span class="legend-item"><span class="legend-dot" style="background:var(--series-sequential)"></span>{esc(week_label)}</span>'
        '</div>'
    )
    return legend + "".join(parts)


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


POST_CHANNEL_ORDER = ["Facebook", "Instagram", "TikTok", "Google Business"]


def post_channel_chips(posts_channels):
    """Small direct-labeled pills tracing which network each post came from.
    Only channels the property is connected to (present in the dict) are
    shown; zero-post channels still show so 'no posts here this week' is
    explicit, not a gap."""
    chips = []
    for channel in POST_CHANNEL_ORDER:
        if channel not in posts_channels:
            continue
        count = posts_channels[channel]
        color_key = f"ch-{channel.lower().replace(' ', '-')}"
        label = "GBP" if channel == "Google Business" else channel
        muted = ' style="opacity:0.45"' if count == 0 else ""
        chips.append(
            f'<span class="channel-chip"{muted}>'
            f'<span class="channel-dot" style="background:var(--{color_key})"></span>'
            f'{esc(label)} {count}</span>'
        )
    return "".join(chips)


def property_card(p, maxes):
    color_key = f"ch-{p['top_channel'].lower().replace(' ', '-')}"
    rows = []
    for key, label in [("followers", "Followers"), ("engagement", "Engagement"), ("views", "Views")]:
        d = p[key]
        bar = mini_bar(d["current"], maxes[key], color_key, height=7, width=72)
        rows.append(f'''
        <div class="metric-row">
          <div class="metric-label">{label}</div>
          <div class="metric-bar">{bar}</div>
          <div class="metric-value">{fmt(d["current"])}</div>
          <div class="metric-delta">{delta_chip(d["current"], d["delta"])}</div>
        </div>''')
    posts_row = f'''
        <div class="metric-row posts-row">
          <div class="metric-label">Posts</div>
          <div class="metric-value posts-total">{fmt(p["posts"]["current"])}</div>
          <div class="channel-chips">{post_channel_chips(p["posts_channels"])}</div>
        </div>'''
    return f'''
    <div class="property-card">
      <div class="property-card-head">
        <h3>{esc(p["name"])}</h3>
        <span class="top-channel-badge" style="border-color:var(--{color_key}); color:var(--{color_key})">{esc(p["top_channel"])}</span>
      </div>
      {posts_row}
      {"".join(rows)}
    </div>'''


def stat_tile(label, current, delta, is_new=False, prev_override=None, compare_label="",
              editable_key=None, week_id=None):
    """editable_key + week_id turn this tile into a manually-editable one --
    Metricool doesn't track this metric (GBP specials, Facebook Groups), so a
    person has to type the real number in. Since the site is static (no
    backend), the edit is saved to the viewer's own browser (localStorage),
    scoped to this metric + this week."""
    prev = prev_override if prev_override is not None else current - delta
    peak = max(current, prev, 1)
    bar = f'''
      <svg class="stat-spark" width="100%" height="18" viewBox="0 0 100 18" preserveAspectRatio="none" role="img" aria-hidden="true">
        <rect x="0" y="10" width="{(prev/peak)*100:.1f}" height="6" rx="3" fill="var(--track)"/>
        <rect x="0" y="0" width="{(current/peak)*100:.1f}" height="6" rx="3" fill="var(--series-sequential)"/>
      </svg>'''
    edit_attrs = ""
    edit_btn = ""
    edit_form = ""
    edited_badge = ""
    if editable_key:
        edit_attrs = (f' data-editable="1" data-metric="{esc(editable_key)}" '
                      f'data-week="{esc(week_id)}" data-current="{current}" data-prev="{prev}"')
        edit_btn = '<button class="edit-btn" type="button" title="Edit this number">✎</button>'
        edit_form = (
            '<div class="edit-form">'
            f'<input type="number" inputmode="numeric" step="1" value="{current}">'
            '<button type="button" class="save">Save</button>'
            '<button type="button" class="cancel">Cancel</button>'
            '</div>'
        )
        edited_badge = '<div class="edited-badge">Manually edited</div>'
    return f'''
    <div class="stat-tile"{edit_attrs}>
      {edit_btn}
      <div class="stat-label">{esc(label)}</div>
      {edited_badge}
      {edit_form}
      <div class="stat-value">{fmt(current)}</div>
      <div class="stat-delta">{delta_chip(current, delta, is_new=is_new, compare_label=compare_label)}</div>
      {bar}
    </div>'''


def build(data_path: Path) -> str:
    data = json.loads(data_path.read_text())

    kpis = data["kpis"]
    kpi_html = "".join([
        stat_tile("Followers", kpis["followers"]["current"], kpis["followers"]["delta"], compare_label="vs last wk"),
        stat_tile("Posts", kpis["posts"]["current"], kpis["posts"]["delta"], compare_label="vs last wk"),
        stat_tile("Engagement", kpis["engagement"]["current"], kpis["engagement"]["delta"], compare_label="vs last wk"),
        stat_tile("Views", kpis["views"]["current"], kpis["views"]["delta"], compare_label="vs last wk"),
    ])
    wow_chart = wow_totals_chart(kpis, data["week_label"], data["prev_week_label"])

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

    week_id = data["week_label"]
    fg = data["facebook_groups"]
    fg_html = "".join([
        stat_tile("Groups posted in", fg["groups_posted_in"]["current"], fg["groups_posted_in"]["delta"],
                   editable_key="fbg_groups_posted_in", week_id=week_id),
        stat_tile("Group likes", fg["group_likes"]["current"], fg["group_likes"]["delta"],
                   editable_key="fbg_group_likes", week_id=week_id),
        stat_tile("Group comments", fg["group_comments"]["current"], fg["group_comments"]["delta"],
                   editable_key="fbg_group_comments", week_id=week_id),
    ])

    gmb = data["google_business"]
    gmb_html = "".join([
        stat_tile("Scheduled posts", gmb["scheduled_posts"]["current"], gmb["scheduled_posts"]["delta"], is_new=gmb["scheduled_posts"].get("is_new", False)),
        stat_tile("Specials posts", gmb["specials_posts"]["current"], gmb["specials_posts"]["delta"], is_new=gmb["specials_posts"].get("is_new", False),
                   editable_key="gbp_specials_posts", week_id=week_id),
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
    out = out.replace("{{WOW_CHART}}", wow_chart)
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
