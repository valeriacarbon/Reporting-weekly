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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gbp_window import assert_matching_windows, resolve_gbp_windows

REPO_ROOT = Path(__file__).resolve().parent.parent

# The Google My Business section still computes and stores week-over-week
# deltas (the completeness gate and the build assertions in
# _check_gbp_window depend on GBP_PRIOR being pulled), it just doesn't show
# them -- Val asked to drop the comparison line and mini bar from the GBP
# tiles as a presentation-only change. Flip back to True to restore them
# without touching any other code.
GBP_SHOW_DELTAS = False

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

# Fixed stacking/legend order for the by-channel bar breakdown -- same order
# and colors (from CHANNEL_COLORS) everywhere a channel stack appears, so the
# color-to-channel mapping never shifts between metrics or sections.
CHANNEL_ORDER = ["TikTok", "Instagram", "Facebook", "Google Business"]


def _channel_css_var(channel):
    return f"ch-{channel.lower().replace(' ', '-')}"


def _channel_short_label(channel):
    return "GBP" if channel == "Google Business" else channel


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


def _rounded_top_rect_path(x, y, w, h, r):
    """Path for a rect rounded on its top two corners only, square at the
    baseline -- lets a stacked bar keep the same rounded-top silhouette as a
    solid bar while its interior segment boundaries are plain straight-across
    rects (clipped to this path), per the dataviz skill's mark spec."""
    r = min(r, w / 2, h) if h > 0 else 0
    return (
        f"M{x:.2f},{y + h:.2f} "
        f"L{x:.2f},{y + r:.2f} "
        f"Q{x:.2f},{y:.2f} {x + r:.2f},{y:.2f} "
        f"L{x + w - r:.2f},{y:.2f} "
        f"Q{x + w:.2f},{y:.2f} {x + w:.2f},{y + r:.2f} "
        f"L{x + w:.2f},{y + h:.2f} Z"
    )


def wow_totals_chart(kpis, week_label, prev_week_label, channel_breakdowns):
    """Grouped bar chart (log scale) comparing this week vs last week across
    all four portfolio KPIs in one view -- they differ by orders of magnitude
    (posts in the tens, views in the tens of thousands), so a shared linear
    axis would flatten the smaller ones to invisible slivers.

    The "last week" bar stays exactly what it was: one solid mark, a single
    total, nothing to break down. The "this week" bar is stacked by channel
    (TikTok/Instagram/Facebook/Google Business, CHANNEL_ORDER, same colors
    used everywhere else in the report) so this week's composition is visible
    at a glance -- only the internal fill of that one bar changes; its
    position, height and the log axis underneath are computed exactly as
    before, so the two bars stay perfectly comparable.

    channel_breakdowns maps each metric label to its list of
    {"channel", "current"} dicts (e.g. data["views_by_channel"]) -- a channel
    absent from a given metric (Google Business has no "Followers") is
    treated as zero and simply doesn't get a segment.
    """
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
    seg_gap = 2  # surface gap between stacked segments, per the mark spec

    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" height="auto" role="img" '
             f'aria-label="This week vs last week, all portfolio KPIs, log scale, '
             f'this week broken down by channel">']

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

        # Last week: unchanged -- one solid mark, one total.
        parts.append(
            f'<rect x="{prev_x:.1f}" y="{prev_y:.1f}" width="{bar_w:.1f}" '
            f'height="{base_y - prev_y:.1f}" rx="4" fill="var(--compare-prev)">'
            f'<title>{esc(prev_week_label)} {esc(label)}: {fmt(prev)}</title></rect>'
        )

        # This week: stacked by channel, clipped to the bar's rounded-top
        # silhouette so the composite still reads as a single mark. Falls
        # back to the old solid bar for a metric whose breakdown isn't in
        # the data file yet (older weekly snapshots), rather than rendering
        # an empty bar.
        breakdown = channel_breakdowns.get(label)
        if breakdown is None:
            parts.append(
                f'<rect x="{curr_x:.1f}" y="{curr_y:.1f}" width="{bar_w:.1f}" '
                f'height="{base_y - curr_y:.1f}" rx="4" fill="var(--series-sequential)">'
                f'<title>{esc(week_label)} {esc(label)}: {fmt(current)}</title></rect>'
            )
        else:
            by_channel = {c["channel"]: c["current"] for c in breakdown}
            segments = []
            cum = 0
            for channel in CHANNEL_ORDER:
                seg_value = by_channel.get(channel, 0)
                if seg_value <= 0:
                    continue
                seg_top = y_of(cum + seg_value)
                seg_bottom = y_of(cum) if cum > 0 else base_y
                segments.append((channel, seg_value, seg_top, seg_bottom))
                cum += seg_value

            clip_id = f"wowclip-{i}"
            parts.append(f'<clipPath id="{clip_id}"><path d="'
                          f'{_rounded_top_rect_path(curr_x, curr_y, bar_w, base_y - curr_y, 4)}"/></clipPath>')
            parts.append(f'<g clip-path="url(#{clip_id})">')
            min_seg_h = 1.5  # a real, nonzero channel never fully disappears on the log scale
            for idx, (channel, seg_value, seg_top, seg_bottom) in enumerate(segments):
                y0 = seg_top + (0 if idx == len(segments) - 1 else seg_gap / 2)
                y1 = seg_bottom - (0 if idx == 0 else seg_gap / 2)
                if y1 - y0 < min_seg_h:
                    y0 = min(y0, y1 - min_seg_h)
                parts.append(
                    f'<rect x="{curr_x:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" '
                    f'height="{max(y1 - y0, 0):.1f}" fill="var(--{_channel_css_var(channel)})">'
                    f'<title>{esc(_channel_short_label(channel))}: {fmt(seg_value)}</title></rect>'
                )
            parts.append('</g>')

        parts.append(f'<text x="{prev_x + bar_w/2:.1f}" y="{prev_y - 8:.1f}" text-anchor="middle" '
                      f'class="wow-value-label">{fmt(prev)}</text>')
        parts.append(f'<text x="{curr_x + bar_w/2:.1f}" y="{curr_y - 8:.1f}" text-anchor="middle" '
                      f'class="wow-value-label">{fmt(current)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{base_y + 20:.1f}" text-anchor="middle" '
                      f'class="wow-cat-label">{esc(label)}</text>')

    parts.append(f'<line x1="{left_pad}" y1="{top_pad + plot_h:.1f}" x2="{W - right_pad}" '
                  f'y2="{top_pad + plot_h:.1f}" stroke="var(--baseline)" stroke-width="1.5"/>')
    parts.append("</svg>")

    week_legend = (
        '<div class="wow-legend">'
        f'<span class="legend-item"><span class="legend-dot" style="background:var(--compare-prev)"></span>{esc(prev_week_label)}</span>'
        f'<span class="legend-item"><span class="legend-dot" style="background:var(--series-sequential)"></span>{esc(week_label)}</span>'
        '</div>'
    )
    channel_legend = "".join(
        f'<span class="legend-item">'
        f'<span class="legend-dot" style="background:var(--{_channel_css_var(ch)})"></span>'
        f'{esc(_channel_short_label(ch))}</span>'
        for ch in CHANNEL_ORDER
    )
    channel_legend_html = f'<div class="wow-legend channel-legend">{channel_legend}</div>'
    return week_legend + channel_legend_html + "".join(parts)


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


def url_tracking_card(p, maxes):
    rows = []
    for key, label in [("views", "Views"), ("sessions", "Sessions"), ("engaged_sessions", "Engaged"), ("tours", "Tours")]:
        value = p[key]
        bar = mini_bar(value, maxes[key], "series-sequential", height=7, width=72)
        rows.append(f'''
        <div class="metric-row">
          <div class="metric-label">{label}</div>
          <div class="metric-bar">{bar}</div>
          <div class="metric-value">{fmt(value)}</div>
        </div>''')
    return f'''
    <div class="property-card">
      <div class="property-card-head">
        <h3>{esc(p["name"])}</h3>
      </div>
      {"".join(rows)}
    </div>'''


def gmb_url_tracking_card(p, maxes):
    rows = []
    for key, label in [("views", "Views"), ("sessions", "Sessions"), ("engaged_sessions", "Engaged"), ("key_events", "Key events")]:
        value = p[key]
        bar = mini_bar(value, maxes[key], "series-sequential", height=7, width=72)
        rows.append(f'''
        <div class="metric-row">
          <div class="metric-label">{label}</div>
          <div class="metric-bar">{bar}</div>
          <div class="metric-value">{fmt(value)}</div>
        </div>''')
    return f'''
    <div class="property-card">
      <div class="property-card-head">
        <h3>{esc(p["name"])}</h3>
      </div>
      {"".join(rows)}
    </div>'''


def gbp_metric_row(label, value, max_value, is_total=False):
    if is_total:
        return f'''
        <div class="metric-row gbp-total-row">
          <div class="metric-label">{esc(label)}</div>
          <div class="metric-value gbp-total-value">{fmt(value)}</div>
        </div>'''
    bar = mini_bar(value, max_value, "series-sequential", height=7, width=72)
    return f'''
        <div class="metric-row">
          <div class="metric-label">{esc(label)}</div>
          <div class="metric-bar">{bar}</div>
          <div class="metric-value">{fmt(value)}</div>
        </div>'''


def gbp_property_card(p, maxes):
    reach_total = p["reach_search"] + p["reach_maps"]
    clicks_total = p["website_clicks"] + p["phone_clicks"] + p["directions_clicks"]
    posts_rows = "".join([
        gbp_metric_row("Published", p["posts_published"], maxes["posts_published"]),
    ])
    reach_rows = "".join([
        gbp_metric_row("Search", p["reach_search"], maxes["reach_search"]),
        gbp_metric_row("Maps", p["reach_maps"], maxes["reach_maps"]),
        gbp_metric_row("Total reach", reach_total, maxes["reach_total"], is_total=True),
    ])
    click_rows = "".join([
        gbp_metric_row("Website", p["website_clicks"], maxes["website_clicks"]),
        gbp_metric_row("Phone", p["phone_clicks"], maxes["phone_clicks"]),
        gbp_metric_row("Directions", p["directions_clicks"], maxes["directions_clicks"]),
        gbp_metric_row("Total clicks", clicks_total, maxes["clicks_total"], is_total=True),
    ])
    return f'''
    <div class="property-card">
      <div class="property-card-head">
        <h3>{esc(p["name"])}</h3>
      </div>
      <div class="gbp-group-label">Posts</div>
      {posts_rows}
      <div class="gbp-group-label">Reach</div>
      {reach_rows}
      <div class="gbp-group-label">Clicks</div>
      {click_rows}
    </div>'''


def channel_delta_chips(fbc):
    """Small per-channel net-gain chips shown directly on the Followers KPI
    tile -- so the split by network (TikTok, Facebook, Instagram, GBP) is
    visible at a glance instead of only further down the report."""
    chips = []
    for c in fbc:
        channel = c["channel"]
        delta = c["delta"]
        color_key = f"ch-{channel.lower().replace(' ', '-')}"
        label = "GBP" if channel == "Google Business" else channel
        if delta > 0:
            arrow, color_var, sign = "▲", "var(--good)", "+"
        elif delta < 0:
            arrow, color_var, sign = "▼", "var(--bad)", ""
        else:
            arrow, color_var, sign = "•", "var(--flat)", ""
        chips.append(
            f'<span class="channel-chip">'
            f'<span class="channel-dot" style="background:var(--{color_key})"></span>'
            f'{esc(label)} <span style="color:{color_var}">{arrow} {sign}{delta:,}</span></span>'
        )
    return "".join(chips)


def channel_value_chips(channels):
    """Small per-channel chips showing this week's raw value, no delta --
    used where we don't have a reliable per-channel history to compare
    against yet (e.g. Engagement's Google Business breakdown, added the
    week GBP clicks were folded into the portfolio Engagement total)."""
    chips = []
    for c in channels:
        channel = c["channel"]
        value = c["current"]
        color_key = f"ch-{channel.lower().replace(' ', '-')}"
        label = "GBP" if channel == "Google Business" else channel
        chips.append(
            f'<span class="channel-chip">'
            f'<span class="channel-dot" style="background:var(--{color_key})"></span>'
            f'{esc(label)} {fmt(value)}</span>'
        )
    return "".join(chips)


def stat_tile(label, current, delta, is_new=False, prev_override=None, compare_label="",
              editable_key=None, week_id=None, channel_breakdown_html="", show_delta=True):
    """editable_key + week_id turn this tile into a manually-editable one --
    Metricool doesn't track this metric (GBP specials, Facebook Groups), so a
    person has to type the real number in. Since the site is static (no
    backend), the edit is saved to the viewer's own browser (localStorage),
    scoped to this metric + this week.

    show_delta=False drops the comparison line (arrow/change/percentage) and
    the mini comparison bar entirely -- not hidden, not rendered -- leaving
    just the label and the number. Used by the GBP section, which still
    computes deltas internally (the window-completeness gate depends on
    them) but doesn't display them."""
    prev = prev_override if prev_override is not None else current - delta
    peak = max(current, prev, 1)
    bar = f'''
      <svg class="stat-spark" width="100%" height="18" viewBox="0 0 100 18" preserveAspectRatio="none" role="img" aria-hidden="true">
        <rect x="0" y="10" width="{(prev/peak)*100:.1f}" height="6" rx="3" fill="var(--track)"/>
        <rect x="0" y="0" width="{(current/peak)*100:.1f}" height="6" rx="3" fill="var(--series-sequential)"/>
      </svg>''' if show_delta else ""
    delta_html = (
        f'<div class="stat-delta">{delta_chip(current, delta, is_new=is_new, compare_label=compare_label)}</div>'
        if show_delta else ""
    )
    edit_attrs = ""
    edit_btn = ""
    edit_form = ""
    edited_badge = ""
    if editable_key:
        edit_attrs = (f' data-editable="1" data-metric="{esc(editable_key)}" '
                      f'data-week="{esc(week_id)}" data-current="{current}" data-prev="{prev}"')
        edit_btn = (
            '<button class="edit-btn" type="button" title="Edit this number">'
            '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>'
            '</svg> Edit</button>'
        )
        edit_form = (
            '<div class="edit-form">'
            f'<input type="number" inputmode="numeric" step="1" value="{current}">'
            '<button type="button" class="save">Save</button>'
            '<button type="button" class="cancel">Cancel</button>'
            '</div>'
        )
        edited_badge = '<div class="edited-badge">Manually edited</div>'
    breakdown_html = (
        f'<div class="stat-channel-breakdown">{channel_breakdown_html}</div>'
        if channel_breakdown_html else ""
    )
    return f'''
    <div class="stat-tile"{edit_attrs}>
      {edit_btn}
      <div class="stat-label">{esc(label)}</div>
      {edited_badge}
      {edit_form}
      <div class="stat-value">{fmt(current)}</div>
      {delta_html}
      {breakdown_html}
      {bar}
    </div>'''


def combo_stat_tile(label, groups_current, groups_delta, posts_current, posts_delta,
                     editable_key, week_id):
    """One card holding two paired counts (e.g. groups posted in + total posts
    across them) instead of splitting them into two separate stat tiles.
    Manually edited like the other Facebook Group tiles -- two number inputs
    saved together under one localStorage key."""
    groups_prev = groups_current - groups_delta
    posts_prev = posts_current - posts_delta
    edit_attrs = (f' data-editable-combo="1" data-metric="{esc(editable_key)}" data-week="{esc(week_id)}" '
                  f'data-groups-current="{groups_current}" data-groups-prev="{groups_prev}" '
                  f'data-posts-current="{posts_current}" data-posts-prev="{posts_prev}"')
    edit_btn = (
        '<button class="edit-btn" type="button" title="Edit these numbers">'
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>'
        '</svg> Edit</button>'
    )
    edit_form = f'''
    <div class="edit-form combo-edit-form">
      <div class="combo-field"><label>Groups</label><input type="number" inputmode="numeric" step="1" class="combo-groups-input" value="{groups_current}"></div>
      <div class="combo-field"><label>Posts</label><input type="number" inputmode="numeric" step="1" class="combo-posts-input" value="{posts_current}"></div>
      <div class="combo-actions"><button type="button" class="save">Save</button><button type="button" class="cancel">Cancel</button></div>
    </div>'''
    return f'''
    <div class="stat-tile combo-tile"{edit_attrs}>
      {edit_btn}
      <div class="stat-label">{esc(label)}</div>
      <div class="edited-badge">Manually edited</div>
      {edit_form}
      <div class="combo-value">
        <span class="combo-num groups-num">{fmt(groups_current)}</span><span class="combo-label">groups</span>
        <span class="combo-sep">/</span>
        <span class="combo-num posts-num">{fmt(posts_current)}</span><span class="combo-label">posts</span>
      </div>
      <div class="combo-deltas">
        <span class="groups-delta">{delta_chip(groups_current, groups_delta)}</span>
        <span class="posts-delta">{delta_chip(posts_current, posts_delta)}</span>
      </div>
    </div>'''


def _check_gbp_window(data):
    """Build-time guard for the GBP posts_published boundary bug: both the
    getScheduledPosts count and the getAnalyticsDataByMetrics pull must have
    been derived from the exact same GBP_CURRENT/GBP_PRIOR window. The data
    file records that single window in `gbp_window`; here we re-derive it
    from scratch with resolve_gbp_windows() and fail loudly if the stored
    window drifted from what that single source of truth would produce, and
    cross-check that the per-property posts_published sums to the headline
    total (a divergence there means the two were computed from different
    windows even if the stored dates match)."""
    gbp_window = data.get("gbp_window")
    if not gbp_window:
        return  # older weekly files predate the independent-window feature

    current_start = date.fromisoformat(gbp_window["current"]["start"])
    current_end = date.fromisoformat(gbp_window["current"]["end"])
    prior_start = date.fromisoformat(gbp_window["prior"]["start"])
    prior_end = date.fromisoformat(gbp_window["prior"]["end"])

    expected = resolve_gbp_windows(current_start)
    assert_matching_windows(
        (current_start, current_end),
        (expected["current_start"], expected["current_end"]),
        label="GBP_CURRENT",
    )
    assert_matching_windows(
        (prior_start, prior_end),
        (expected["prior_start"], expected["prior_end"]),
        label="GBP_PRIOR",
    )

    gbp_props = data.get("gbp_by_property", [])
    if gbp_props and all("posts_published" in p for p in gbp_props):
        per_property_sum = sum(p["posts_published"] for p in gbp_props)
        headline = data["google_business"]["posts_published"]["current"]
        if per_property_sum != headline:
            raise AssertionError(
                f"GBP posts_published mismatch: per-property sum ({per_property_sum}) "
                f"!= headline total ({headline}). Every property's posts_published must "
                f"be recomputed from the same GBP_CURRENT window as the headline number "
                f"-- see scripts/gbp_window.py."
            )


def build(data_path: Path) -> str:
    data = json.loads(data_path.read_text())

    kpis = data["kpis"]
    fbc = data["followers_by_channel"]
    ebc = data.get("engagement_by_channel")
    kpi_html = "".join([
        stat_tile("Followers", kpis["followers"]["current"], kpis["followers"]["delta"], compare_label="vs last wk",
                   channel_breakdown_html=channel_delta_chips(fbc)),
        stat_tile("Posts", kpis["posts"]["current"], kpis["posts"]["delta"], compare_label="vs last wk"),
        stat_tile("Engagement", kpis["engagement"]["current"], kpis["engagement"]["delta"], compare_label="vs last wk",
                   channel_breakdown_html=channel_value_chips(ebc) if ebc else ""),
        stat_tile("Views", kpis["views"]["current"], kpis["views"]["delta"], compare_label="vs last wk"),
    ])
    channel_breakdowns = {
        "Followers": fbc,
        "Posts": data.get("posts_by_channel"),
        "Engagement": ebc,
        "Views": data.get("views_by_channel"),
    }
    wow_chart = wow_totals_chart(kpis, data["week_label"], data["prev_week_label"], channel_breakdowns)

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
    gp = fg["groups_and_posts"]
    fg_html = "".join([
        stat_tile("Properties posted this week", fg["groups_posted_in"]["current"], fg["groups_posted_in"]["delta"],
                   editable_key="fbg_groups_posted_in", week_id=week_id),
        combo_stat_tile("Groups Posted In / Posts", gp["groups"]["current"], gp["groups"]["delta"],
                        gp["posts"]["current"], gp["posts"]["delta"],
                        editable_key="fbg_groups_and_posts", week_id=week_id),
        stat_tile("Interactions (likes, comments, shares)", fg["interactions"]["current"], fg["interactions"]["delta"],
                   editable_key="fbg_interactions", week_id=week_id),
    ])

    gmb = data["google_business"]
    _check_gbp_window(data)
    gbp_window_label = data.get("gbp_window_label", data["week_label"])
    gbp_prev_window_label = data.get("gbp_prev_window_label", data["prev_week_label"])
    gbp_compare_label = f"vs {gbp_prev_window_label}"
    gmb_html = "".join([
        stat_tile("Posts published", gmb["posts_published"]["current"], gmb["posts_published"]["delta"], is_new=gmb["posts_published"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
        stat_tile("Reach · search", gmb["reach_search"]["current"], gmb["reach_search"].get("delta", 0), is_new=gmb["reach_search"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
        stat_tile("Reach · maps", gmb["reach_maps"]["current"], gmb["reach_maps"].get("delta", 0), is_new=gmb["reach_maps"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
        stat_tile("Website clicks", gmb["website_clicks"]["current"], gmb["website_clicks"].get("delta", 0), is_new=gmb["website_clicks"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
        stat_tile("Phone clicks", gmb["phone_clicks"]["current"], gmb["phone_clicks"].get("delta", 0), is_new=gmb["phone_clicks"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
        stat_tile("Directions clicks", gmb["directions_clicks"]["current"], gmb["directions_clicks"].get("delta", 0), is_new=gmb["directions_clicks"].get("is_new", False), compare_label=gbp_compare_label, show_delta=GBP_SHOW_DELTAS),
    ])
    gmb_window_note = (
        f"Google's own reporting lags the rest of this dashboard by 1–2 weeks, so these "
        f"six tiles (and the per-property cards below) use their own, independently-detected "
        f"window instead of this week's <strong>{esc(data['week_label'])}</strong>: the most "
        f"recent week where every Google Business property had complete daily data, "
        f"<strong>{esc(gbp_window_label)}</strong>, compared against the fully-synced week "
        f"before it, <strong>{esc(gbp_prev_window_label)}</strong>."
    )

    gbp_props = data.get("gbp_by_property", [])
    gbp_maxes = {}
    if gbp_props:
        reach_totals = [p["reach_search"] + p["reach_maps"] for p in gbp_props]
        clicks_totals = [p["website_clicks"] + p["phone_clicks"] + p["directions_clicks"] for p in gbp_props]
        gbp_maxes = {
            "posts_published": max(p["posts_published"] for p in gbp_props),
            "reach_search": max(p["reach_search"] for p in gbp_props),
            "reach_maps": max(p["reach_maps"] for p in gbp_props),
            "reach_total": max(reach_totals),
            "website_clicks": max(p["website_clicks"] for p in gbp_props),
            "phone_clicks": max(p["phone_clicks"] for p in gbp_props),
            "directions_clicks": max(p["directions_clicks"] for p in gbp_props),
            "clicks_total": max(clicks_totals),
        }
    gbp_property_cards = "".join(gbp_property_card(p, gbp_maxes) for p in gbp_props)

    gmb_url_tracking = data.get("gmb_url_tracking")
    gmb_url_tracking_section = ""
    if gmb_url_tracking:
        gmb_ut_html = "".join([
            stat_tile("Views", gmb_url_tracking["views"]["current"], gmb_url_tracking["views"].get("delta", 0), is_new=gmb_url_tracking["views"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Sessions", gmb_url_tracking["sessions"]["current"], gmb_url_tracking["sessions"].get("delta", 0), is_new=gmb_url_tracking["sessions"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Engaged sessions", gmb_url_tracking["engaged_sessions"]["current"], gmb_url_tracking["engaged_sessions"].get("delta", 0), is_new=gmb_url_tracking["engaged_sessions"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Key events", gmb_url_tracking["key_events"]["current"], gmb_url_tracking["key_events"].get("delta", 0), is_new=gmb_url_tracking["key_events"].get("is_new", False), compare_label="vs last wk"),
        ])
        gut_props = gmb_url_tracking.get("by_property", [])
        gut_maxes = {
            "views": max((p["views"] for p in gut_props), default=1),
            "sessions": max((p["sessions"] for p in gut_props), default=1),
            "engaged_sessions": max((p["engaged_sessions"] for p in gut_props), default=1),
            "key_events": max((p["key_events"] for p in gut_props), default=1),
        }
        gmb_ut_cards = "".join(gmb_url_tracking_card(p, gut_maxes) for p in gut_props)
        gmb_url_tracking_section = f'''
  <section>
    <h2>Google My Business — URL Tracking</h2>
    <p class="section-sub">Traffic that lands on each property's site from its Google Business Profile (Google Analytics, source: GMB / GMB).</p>
    <div class="stat-grid">{gmb_ut_html}</div>
    <dl class="legend">
      <div class="legend-item"><dt>Views</dt><dd>The number of times the page was loaded/viewed, including repeat views from the same person or session.</dd></div>
      <div class="legend-item"><dt>Sessions</dt><dd>Total number of visits per person.</dd></div>
      <div class="legend-item"><dt>Engaged sessions</dt><dd>A session that lasted 10+ seconds, visited more than one page, or triggered a conversion event.</dd></div>
      <div class="legend-item"><dt>Key events</dt><dd>Conversion events tracked on the site (e.g. tour requests).</dd></div>
    </dl>
  </section>

  <section>
    <h2>Google My Business — URL Tracking by brand</h2>
    <p class="section-sub">Quick view per property.</p>
    <div class="property-grid">{gmb_ut_cards}</div>
    <div class="note-box">{esc(gmb_url_tracking["note"])}</div>
  </section>'''

    url_tracking = data.get("url_tracking")
    url_tracking_section = ""
    if url_tracking:
        url_tracking_html = "".join([
            stat_tile("Views", url_tracking["views"]["current"], url_tracking["views"].get("delta", 0), is_new=url_tracking["views"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Sessions", url_tracking["sessions"]["current"], url_tracking["sessions"].get("delta", 0), is_new=url_tracking["sessions"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Engaged sessions", url_tracking["engaged_sessions"]["current"], url_tracking["engaged_sessions"].get("delta", 0), is_new=url_tracking["engaged_sessions"].get("is_new", False), compare_label="vs last wk"),
            stat_tile("Tours", url_tracking["tours"]["current"], url_tracking["tours"].get("delta", 0), is_new=url_tracking["tours"].get("is_new", False), compare_label="vs last wk"),
        ])
        ut_props = url_tracking.get("by_property", [])
        ut_maxes = {
            "views": max((p["views"] for p in ut_props), default=1),
            "sessions": max((p["sessions"] for p in ut_props), default=1),
            "engaged_sessions": max((p["engaged_sessions"] for p in ut_props), default=1),
            "tours": max((p["tours"] for p in ut_props), default=1),
        }
        url_tracking_cards = "".join(url_tracking_card(p, ut_maxes) for p in ut_props)
        url_tracking_section = f'''
  <section>
    <h2>URL Tracking</h2>
    <p class="section-sub">Traffic from Facebook Group posts landing on each property's site (Google Analytics).</p>
    <div class="stat-grid">{url_tracking_html}</div>
    <dl class="legend">
      <div class="legend-item"><dt>Views</dt><dd>The number of times the page was loaded/viewed, including repeat views from the same person or session.</dd></div>
      <div class="legend-item"><dt>Sessions</dt><dd>Total number of visits per person.</dd></div>
      <div class="legend-item"><dt>Engaged sessions</dt><dd>A session that lasted 10+ seconds, visited more than one page, or triggered a conversion event.</dd></div>
      <div class="legend-item"><dt>Tours</dt><dd>Tours booked.</dd></div>
    </dl>
  </section>

  <section>
    <h2>URL Tracking — by brand</h2>
    <p class="section-sub">Quick view per property.</p>
    <div class="property-grid">{url_tracking_cards}</div>
    <div class="note-box">{esc(url_tracking["note"])}</div>
  </section>'''

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
    out = out.replace("{{GMB_WINDOW_NOTE}}", gmb_window_note)
    out = out.replace("{{GBP_WINDOW_LABEL}}", esc(gbp_window_label))
    out = out.replace("{{GBP_PROPERTY_CARDS}}", gbp_property_cards)
    out = out.replace("{{GMB_URL_TRACKING_SECTION}}", gmb_url_tracking_section)
    out = out.replace("{{URL_TRACKING_SECTION}}", url_tracking_section)
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
