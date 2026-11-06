#!/usr/bin/env python3
"""
Builds the Organic Brief: a short 16:9 HTML slide deck that sits on top of
the same weekly data file the Detail Pack (index.html) is built from.

Usage:
    python3 scripts/build_brief.py data/week-YYYY-MM-DD.json [--config config/organic_brief.json]

Writes organic-brief_YYYY-MM-DD.html at the repo root, next to index.html.
It never touches index.html or build_report.py.

Every number comes from the data layer:
  - this week   = the given data/week-*.json file
  - last week   = the most recent data/week-*.json dated before it
  - GBP property comparison = the data file whose gbp_window.current equals
    this file's gbp_window.prior (GBP runs on its own lagged window)
Ranking logic lives in config/organic_brief.json. A slide whose source is
missing renders "No data" instead of failing the build.
"""
import argparse
import html
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DEFAULT_CONFIG = REPO_ROOT / "config" / "organic_brief.json"

# Same channel colors as the Detail Pack's light mode (template.html).
CHANNEL_COLORS = {
    "Facebook": "#2a78d6",
    "TikTok": "#1baf7a",
    "Instagram": "#e87ba4",
    "Google Business": "#eda100",
}

# Simple inline platform glyphs (currentColor), so no external assets are needed.
CHANNEL_ICONS = {
    "Facebook": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="currentColor"/>'
                '<path d="M13.4 19.5v-6h2l.3-2.4h-2.3V9.6c0-.7.2-1.2 1.2-1.2h1.2V6.3c-.2 0-1-.1-1.8-.1-1.8 0-3 1.1-3 3.1v1.8h-2v2.4h2v6z" fill="#fff"/></svg>',
    "Instagram": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="1" width="22" height="22" rx="6.5" fill="currentColor"/>'
                 '<rect x="5.5" y="5.5" width="13" height="13" rx="4" fill="none" stroke="#fff" stroke-width="1.8"/>'
                 '<circle cx="12" cy="12" r="3.1" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="16.3" cy="7.7" r="1" fill="#fff"/></svg>',
    "TikTok": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1" y="1" width="22" height="22" rx="6.5" fill="currentColor"/>'
              '<path d="M13.2 5.5h2.3c.2 1.6 1.2 2.7 2.8 2.9v2.3c-1.1 0-2-.3-2.8-.8v4.6c0 2.4-1.8 4-4 4s-4-1.7-4-4 1.9-4.1 4.4-3.9v2.4c-1.1-.3-2 .4-2 1.5 0 .9.7 1.6 1.6 1.6 1 0 1.7-.7 1.7-1.8z" fill="#fff"/></svg>',
}


def icon(channel, cls="ico"):
    color = CHANNEL_COLORS.get(channel, "#898781")
    return f'<span class="{cls}" style="color:{color}" title="{esc(channel)}">{CHANNEL_ICONS.get(channel, "")}</span>'

WEEK_FILE_RE = re.compile(r"^week-(\d{4}-\d{2}-\d{2})\.json$")


# --------------------------------------------------------------------------
# data helpers
# --------------------------------------------------------------------------

def esc(s):
    return html.escape(str(s), quote=True)


def week_date(path: Path):
    m = WEEK_FILE_RE.match(path.name)
    return m.group(1) if m else None


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def week_files():
    files = [p for p in DATA_DIR.glob("week-*.json") if week_date(p)]
    return sorted(files, key=week_date)


def previous_week_file(data_path: Path):
    this = week_date(data_path)
    earlier = [p for p in week_files() if week_date(p) < this]
    return earlier[-1] if earlier else None


def gbp_prior_file(data):
    """File whose GBP_CURRENT window equals this file's GBP_PRIOR window."""
    prior = (data.get("gbp_window") or {}).get("prior")
    if not prior:
        return None
    for p in reversed(week_files()):
        try:
            cur = (load_json(p).get("gbp_window") or {}).get("current")
        except Exception:
            continue
        if cur == prior:
            return p
    return None


def channel_value(lst, channel, key="current"):
    if not isinstance(lst, list):
        return None
    for row in lst:
        if row.get("channel") == channel:
            v = row.get(key)
            return v if isinstance(v, (int, float)) else None
    return None


def by_name(rows):
    return {r.get("name"): r for r in (rows or []) if isinstance(r, dict)}


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

def fmt(v, kind="int"):
    if v is None:
        return "No data"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "signed":
        return f"{v:+,}"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}"
    return f"{int(round(v)):,}"


def wow(cur, prev):
    """▲/▼ + % change chip, this week vs last week."""
    if cur is None:
        return '<span class="chip na">No data</span>'
    if prev is None:
        return '<span class="chip na">no prior wk</span>'
    if prev == 0:
        if cur == 0:
            return '<span class="chip flat">– 0%</span>'
        arrow, cls = ("▲", "up") if cur > 0 else ("▼", "down")
        return f'<span class="chip {cls}">{arrow} new</span>'
    pct = (cur - prev) / abs(prev) * 100
    if abs(pct) < 0.05:
        return '<span class="chip flat">– 0%</span>'
    arrow, cls = ("▲", "up") if pct > 0 else ("▼", "down")
    return f'<span class="chip {cls}">{arrow} {abs(pct):.1f}%</span>'


def no_data(msg="No data"):
    return f'<div class="nodata">{esc(msg)}</div>'


def platform_tag(platform):
    color = CHANNEL_COLORS.get(platform, "#898781")
    label = "GBP" if platform == "Google Business" else platform
    return f'<span class="tag" style="--c:{color}">{esc(label)}</span>'


def big_tile(label, cur, prev, kind="int", sub=""):
    sub_html = f'<div class="tile-sub">{esc(sub)}</div>' if sub else ""
    return (
        '<div class="tile">'
        f'<div class="tile-label">{esc(label)}</div>'
        f'<div class="tile-value">{fmt(cur, kind)}</div>'
        f'<div class="tile-wow">{wow(cur, prev)}<span class="tile-prev">last wk {fmt(prev, kind) if prev is not None else "—"}</span></div>'
        f"{sub_html}</div>"
    )


# --------------------------------------------------------------------------
# slide 1 — Social Scoreboard
# --------------------------------------------------------------------------

def post_sum(data, platform, metric):
    posts = data.get("social_posts") if data else None
    if not isinstance(posts, list):
        return None
    vals = [num(p.get(metric)) for p in posts if p.get("platform") == platform]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def scoreboard_metrics(data, platforms, cfg):
    """Returns {kpi: {platform|Total: value}} for one week's data file."""
    if not data:
        return None
    out = {k: {} for k in ("reach", "impressions", "er", "followers_gained", "posts")}
    for ch in platforms:
        out["reach"][ch] = post_sum(data, ch, "reach")
        out["impressions"][ch] = channel_value(data.get("views_by_channel"), ch)
        out["followers_gained"][ch] = channel_value(data.get("followers_by_channel"), ch, "delta")
        out["posts"][ch] = channel_value(data.get("posts_by_channel"), ch)
        out.setdefault("_interactions", {})[ch] = channel_value(data.get("engagement_by_channel"), ch)

    def total(kpi):
        vals = [out[kpi][c] for c in platforms]
        return sum(vals) if all(v is not None for v in vals) else None

    for kpi in ("reach", "impressions", "followers_gained", "posts", "_interactions"):
        out[kpi]["Total"] = total(kpi)

    denom_key = "reach" if cfg.get("engagement_rate_denominator") == "reach" else "impressions"
    for col in platforms + ["Total"]:
        inter, den = out["_interactions"][col], out[denom_key][col]
        out["er"][col] = (inter / den) if (inter is not None and den) else None
    out["_denom_label"] = denom_key
    return out


def kpi_card(label, cur, prev, chips_html, show_wow=True):
    wow_html = (f'<div class="kpi-wow">{wow(cur, prev)}<span class="tile-prev">vs last wk {fmt(prev) if prev is not None else "—"}</span></div>'
                if show_wow else '<div class="kpi-wow"><span class="tile-prev">this week</span></div>')
    return (f'<div class="kpi"><div class="kpi-label">{esc(label)}</div>'
            f'<div class="kpi-value">{fmt(cur)}</div>{wow_html}'
            f'<div class="kpi-chips">{chips_html}</div></div>')


def chips(values, platforms):
    return "".join(
        f'<span class="pchip">{icon(c)}<b>{fmt(values.get(c))}</b></span>' for c in platforms
    )


def top_channel(ctx):
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    metric = cfg.get("scoreboard", {}).get("top_channel_metric", "impressions")
    m = scoreboard_metrics(ctx["data"], platforms, cfg.get("scoreboard", {}))
    vals = {c: (m or {}).get(metric, {}).get(c) for c in platforms}
    vals = {c: v for c, v in vals.items() if v is not None}
    return max(vals, key=vals.get) if vals else None


def overview_title(ctx):
    ch = top_channel(ctx)
    return f"Our top channel this week was {ch}" if ch else "Top channel this week: No data"


def slide_overview(ctx):
    """Slide 1: Detail-Pack-style KPI cards, social platforms only."""
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    data, prev = ctx["data"], ctx["prev"]

    def per(d, key, field="current"):
        return {c: channel_value((d or {}).get(key), c, field) for c in platforms}

    def tot(vals):
        v = list(vals.values())
        return sum(v) if v and all(x is not None for x in v) else None

    fol, fol_p = per(data, "followers_by_channel"), per(prev, "followers_by_channel")
    posts = per(data, "posts_by_channel")
    eng, eng_p = per(data, "engagement_by_channel"), per(prev, "engagement_by_channel")
    views, views_p = per(data, "views_by_channel"), per(prev, "views_by_channel")
    if all(tot(x) is None for x in (fol, posts, eng, views)):
        return no_data()
    cards = [
        kpi_card("Followers", tot(fol), tot(fol_p), chips(fol, platforms)),
        kpi_card("Posts this week", tot(posts), None, chips(posts, platforms), show_wow=False),
        kpi_card("Engagement", tot(eng), tot(eng_p), chips(eng, platforms)),
        kpi_card("Views", tot(views), tot(views_p), chips(views, platforms)),
    ]
    return f'<div class="kpis">{"".join(cards)}</div>'


def slide_scoreboard(ctx):
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    cur = scoreboard_metrics(ctx["data"], platforms, cfg.get("scoreboard", {}))
    prev = scoreboard_metrics(ctx["prev"], platforms, cfg.get("scoreboard", {}))
    if cur is None:
        return no_data()
    rows = [
        ("Reach", "reach", "int"),
        ("Impressions", "impressions", "int"),
        (f"Engagement rate <small>(interactions / {cur['_denom_label']})</small>", "er", "pct"),
        ("Followers gained", "followers_gained", "signed_or_int"),
        ("Posts published", "posts", "int"),
    ]
    cols = platforms + ["Total"]
    head = "".join(
        (f'<th class="ph" style="--c:{CHANNEL_COLORS[c]}">{icon(c)}<span>{esc(c)}</span></th>' if c != "Total"
         else '<th class="ph tot"><span>Total</span></th>')
        for c in cols
    )
    body = []
    any_value = False
    for label, key, kind in rows:
        cells = []
        for c in cols:
            v = cur[key].get(c)
            p = prev[key].get(c) if prev else None
            any_value = any_value or v is not None
            k = "signed" if kind == "signed_or_int" and v is not None else ("int" if kind == "signed_or_int" else kind)
            color = CHANNEL_COLORS.get(c, "#52514e")
            if v is None:
                cells.append(f'<td class="cell" style="--c:{color}"><span class="nd">No data</span></td>')
            elif c == "Total":
                cells.append(f'<td class="cell total"><div class="v">{fmt(v, k)}</div>{wow(v, p)}</td>')
            else:
                peers = [abs(cur[key].get(x) or 0) for x in platforms]
                w = abs(v) / max(peers) * 100 if max(peers) else 0
                cells.append(
                    f'<td class="cell" style="--c:{color}"><div class="v">{fmt(v, k)}</div>'
                    f'<div class="bar"><i style="width:{w:.0f}%"></i></div>{wow(v, p)}</td>'
                )
        body.append(f'<tr><th class="rowh">{label}</th>{"".join(cells)}</tr>')
    if not any_value:
        return no_data()
    return f'<table class="score"><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


# --------------------------------------------------------------------------
# slide 2 — Social Wins
# --------------------------------------------------------------------------

def rank_posts(data, cfg, platforms):
    posts = data.get("social_posts") if data else None
    if not isinstance(posts, list):
        return None
    wcfg = cfg.get("social_wins", {})
    sort_m = wcfg.get("sort_metric", "interactions")
    den_m = wcfg.get("denominator_metric", "reach")
    fb_m = wcfg.get("fallback_denominator_metric")
    min_den = wcfg.get("min_denominator", 0) or 0
    tie = wcfg.get("tiebreak_metric", sort_m)
    ranked = []
    for p in posts:
        if p.get("platform") not in platforms:
            continue
        numer = num(p.get(sort_m))
        den, den_used = num(p.get(den_m)), den_m
        if not den and fb_m:
            den, den_used = num(p.get(fb_m)), fb_m
        if numer is None or not den or den < min_den:
            continue
        ranked.append(dict(p, _rate=numer / den, _den_used=den_used, _numer=numer, _den=den))
    ranked.sort(key=lambda r: (r["_rate"], num(r.get(tie)) or 0), reverse=True)
    return ranked[: int(wcfg.get("top_n", 3))]


def slide_wins(ctx):
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    top = rank_posts(ctx["data"], cfg, platforms)
    if not top:
        return no_data("No data — no post-level metrics (social_posts) in this week's data file")
    prev_top = rank_posts(ctx["prev"], cfg, platforms) or []
    sort_m = cfg.get("social_wins", {}).get("sort_metric", "interactions")
    cards = []
    for i, p in enumerate(top):
        thumb = p.get("thumbnail")
        img = (f'<img src="{esc(thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
               if thumb else '<div class="noimg">No thumbnail</div>')
        if p.get("url"):
            img = f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">{img}</a>'
        prev_rate = prev_top[i]["_rate"] if i < len(prev_top) else None
        cards.append(
            '<div class="win">'
            f'<div class="thumb">{img}<span class="rank">#{i + 1}</span></div>'
            f'<div class="win-meta">{platform_tag(p.get("platform"))}<span class="prop">{esc(p.get("property", "—"))}</span></div>'
            f'<div class="win-big">{fmt(p["_rate"], "pct")}</div>'
            f'<div class="win-label">engagement rate ({esc(sort_m)} / {esc(p["_den_used"])})</div>'
            f'<div class="win-wow">{wow(p["_rate"], prev_rate)}<span class="tile-prev">vs last wk #{i + 1}: {fmt(prev_rate, "pct") if prev_rate is not None else "—"}</span></div>'
            f'<div class="win-sub">{fmt(p["_numer"])} {esc(sort_m)} · {fmt(p["_den"])} {esc(p["_den_used"])}</div>'
            "</div>"
        )
    return f'<div class="wins">{"".join(cards)}</div>'


# --------------------------------------------------------------------------
# slide 3 — GMB
# --------------------------------------------------------------------------

def gb_pair(gb, key):
    m = gb.get(key) if isinstance(gb, dict) else None
    if not isinstance(m, dict) or num(m.get("current")) is None:
        return None, None
    cur, d = m["current"], num(m.get("delta"))
    return cur, (cur - d if d is not None else None)


def slide_gmb(ctx):
    data, cfg = ctx["data"], ctx["config"]
    gb = data.get("google_business")
    parts = []
    if not isinstance(gb, dict):
        parts.append(f'<div class="half">{no_data()}</div>')
    else:
        rs, rs_p = gb_pair(gb, "reach_search")
        rm, rm_p = gb_pair(gb, "reach_maps")
        views = rs + rm if rs is not None and rm is not None else None
        views_p = rs_p + rm_p if rs_p is not None and rm_p is not None else None
        tiles = [
            ("Views", views, views_p, "search + maps reach"),
            ("Searches", rs, rs_p, "reach · search"),
            ("Website clicks", *gb_pair(gb, "website_clicks"), ""),
            ("Calls", *gb_pair(gb, "phone_clicks"), ""),
            ("Direction requests", *gb_pair(gb, "directions_clicks"), ""),
            ("Posts published", *gb_pair(gb, "posts_published"), ""),
        ]
        parts.append(
            '<div class="half"><div class="tiles six">'
            + "".join(big_tile(l, c, p, sub=s) for l, c, p, s in tiles)
            + "</div></div>"
        )

    gcfg = cfg.get("gmb_top_properties", {})
    weights = gcfg.get("weights", {})
    props = data.get("gbp_by_property")
    if not isinstance(props, list) or not props or not weights:
        parts.append(f'<div class="half">{no_data()}</div>')
    else:
        prior_path = gbp_prior_file(data)
        prior_rows = by_name(load_json(prior_path).get("gbp_by_property")) if prior_path else {}

        def score(r):
            return sum(w * (num(r.get(m)) or 0) for m, w in weights.items())

        top = sorted(props, key=score, reverse=True)[: int(gcfg.get("top_n", 3))]
        labels = {
            "website_clicks": "Website clicks", "phone_clicks": "Calls",
            "directions_clicks": "Directions", "reach_search": "Searches",
            "reach_maps": "Maps reach", "posts_published": "Posts",
        }
        cards = []
        for i, r in enumerate(top):
            pr = prior_rows.get(r.get("name"))
            mets = "".join(
                f'<div class="m"><span class="ml">{esc(labels.get(m, m))}</span>'
                f'<span class="mv">{fmt(num(r.get(m)))}</span>'
                f'{wow(num(r.get(m)), num(pr.get(m)) if pr else None)}</div>'
                for m in weights
            )
            cards.append(
                f'<div class="gcard"><div class="gname"><span class="rank-s">#{i + 1}</span>{esc(r.get("name"))}'
                f'<span class="score">score {fmt(score(r))}</span></div>{mets}</div>'
            )
        parts.append(f'<div class="half"><div class="half-title">Top {len(top)} GMB properties</div><div class="gcards">{"".join(cards)}</div></div>')
    return "".join(parts)


# --------------------------------------------------------------------------
# slide 4 — Organic URL Tracking
# --------------------------------------------------------------------------

def section_pair(sec, field):
    m = sec.get(field) if isinstance(sec, dict) else None
    if not isinstance(m, dict) or num(m.get("current")) is None:
        return None, None
    cur, d = m["current"], num(m.get("delta"))
    return cur, (cur - d if d is not None else None)


def slide_url(ctx):
    data, prev, cfg = ctx["data"], ctx["prev"], ctx["config"]
    ucfg = cfg.get("url_tracking", {})
    srcs = [("FBGP", ucfg.get("fbgp", {})), ("GMB", ucfg.get("gmb", {}))]
    secs = {k: data.get(s.get("section_key")) for k, s in srcs}
    prev_secs = {k: (prev or {}).get(s.get("section_key")) for k, s in srcs}
    if not any(isinstance(v, dict) for v in secs.values()):
        return no_data()

    tiles, lead_cur, lead_prev = [], [], []
    for k, s in srcs:
        sec = secs[k]
        c_c, c_p = section_pair(sec, s.get("clicks_field"))
        l_c, l_p = section_pair(sec, s.get("leads_field"))
        tiles.append(big_tile(f"{k} clicks", c_c, c_p, sub=s.get("clicks_field", "")))
        tiles.append(big_tile(f"{k} leads", l_c, l_p, sub=s.get("leads_field", "")))
        lead_cur.append(l_c)
        lead_prev.append(l_p)
    tot = sum(lead_cur) if all(v is not None for v in lead_cur) else None
    tot_p = sum(lead_prev) if all(v is not None for v in lead_prev) else None
    tiles.append(big_tile("Total organic leads", tot, tot_p, sub="FBGP + GMB").replace('class="tile"', 'class="tile hero"', 1))

    # by-property table
    names = []
    for sec in secs.values():
        for r in (sec or {}).get("by_property", []) if isinstance(sec, dict) else []:
            if r.get("name") not in names:
                names.append(r.get("name"))
    cur_rows = {k: by_name((secs[k] or {}).get("by_property")) if isinstance(secs[k], dict) else {} for k, _ in srcs}
    prev_rows = {k: by_name((prev_secs[k] or {}).get("by_property")) if isinstance(prev_secs[k], dict) else {} for k, _ in srcs}

    def cell(k, s, name, field_key):
        r = cur_rows[k].get(name)
        if r is None:
            return '<td class="cell"><span class="nd">No data</span></td>'
        v = num(r.get(s.get(field_key)))
        pr = prev_rows[k].get(name)
        p = num(pr.get(s.get(field_key))) if pr else None
        return f'<td class="cell"><div class="v">{fmt(v)}</div>{wow(v, p)}</td>'

    def activity(name):
        leads = sum(num(cur_rows[k].get(name, {}).get(s.get("leads_field"))) or 0 for k, s in srcs)
        clicks = sum(num(cur_rows[k].get(name, {}).get(s.get("clicks_field"))) or 0 for k, s in srcs)
        return leads, clicks

    active = [n for n in names if activity(n) != (0, 0)]
    active.sort(key=activity, reverse=True)
    cap = int(ucfg.get("max_property_rows", 8))
    shown, hidden = active[:cap], len(active) - min(len(active), cap)
    if shown:
        rows = "".join(
            f'<tr><th class="rowh">{esc(n)}</th>'
            + cell("FBGP", srcs[0][1], n, "clicks_field") + cell("FBGP", srcs[0][1], n, "leads_field")
            + cell("GMB", srcs[1][1], n, "clicks_field") + cell("GMB", srcs[1][1], n, "leads_field")
            + "</tr>"
            for n in shown
        )
        more = f'<div class="more">+{hidden} more properties with activity (see Detail Pack)</div>' if hidden else ""
        zero = len(names) - len(active)
        zero_note = f'<div class="more">{zero} properties with no tracked activity not shown</div>' if zero else ""
        table = (
            '<table class="score small"><thead><tr><th class="lh">Property</th><th>FBGP clicks</th><th>FBGP leads</th>'
            f'<th>GMB clicks</th><th>GMB leads</th></tr></thead><tbody>{rows}</tbody></table>{more}{zero_note}'
        )
    else:
        table = no_data("No property-level activity")
    return f'<div class="tiles five">{"".join(tiles)}</div><div class="url-table">{table}</div>'


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

SLIDES = [
    (overview_title, "Social at a glance · TikTok · Facebook · Instagram — portfolio-wide", slide_overview),
    ("Social Scoreboard", "By platform · this week vs last week", slide_scoreboard),
    ("Social Wins", "Top posts of the week by engagement rate", slide_wins),
    ("Google My Business", "Portfolio-wide + top properties", slide_gmb),
    ("Organic URL Tracking", "FB Groups (FBGP) + GMB tracked links", slide_url),
]


def build(data_path: Path, config_path: Path):
    """Returns (html, out_path, log_lines). Never raises for missing data."""
    log = []
    config = load_json(config_path)
    data = load_json(data_path)
    date_str = week_date(data_path) or datetime.now().strftime("%Y-%m-%d")
    prev_path = previous_week_file(data_path)
    prev = load_json(prev_path) if prev_path else None
    log.append(f"this week: {data_path.name} ({data.get('week_label', '?')})")
    log.append(f"last week: {prev_path.name if prev_path else 'NONE'}")
    gp = gbp_prior_file(data)
    log.append(f"GBP property comparison file: {gp.name if gp else 'NONE (property WoW shows no prior wk)'}")

    ctx = {"data": data, "prev": prev, "config": config}
    total = len(SLIDES)
    sections = []
    for i, (title, subtitle, fn) in enumerate(SLIDES, 1):
        if callable(title):
            try:
                title = title(ctx)
            except Exception as e:
                log.append(f"slide {i} title: ERROR {e!r}")
                title = "No data"
        try:
            body = fn(ctx)
        except Exception as e:  # a broken source must not fail the deck
            log.append(f"slide {i} ({title}): ERROR {e!r} -> rendered 'No data'")
            traceback.print_exc(file=sys.stderr)
            body = no_data()
        nd = body.count("No data")
        log.append(f"slide {i} ({title}): ok" + (f" ({nd} 'No data' cell(s))" if nd else ""))
        window = ""
        if fn is slide_gmb and data.get("gbp_window_label"):
            window = f'GBP window {esc(data["gbp_window_label"])} vs {esc(data.get("gbp_prev_window_label", "—"))}'
        sections.append(
            f'<section class="slide" id="s{i}"><div class="frame">'
            f'<header><div><h1>{esc(title)}</h1><div class="sub">{esc(subtitle)}</div></div>'
            f'<div class="meta"><div class="wk">{esc(data.get("week_label", ""))}</div>'
            f'<div class="vs">vs {esc(data.get("prev_week_label", "last week"))}</div></div></header>'
            f'<main>{body}</main>'
            f'<footer><span>Organic Brief · Carbon Residential</span><span>{window}</span><span>{i} / {total}</span></footer>'
            "</div></section>"
        )

    out_path = REPO_ROOT / f'{config.get("output", {}).get("prefix", "organic-brief_")}{date_str}.html'
    page = TEMPLATE.replace("{{TITLE}}", esc(f"Organic Brief {date_str}")).replace("{{SLIDES}}", "\n".join(sections))
    return page, out_path, log


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<style>
  :root {
    color-scheme: light;
    --page:#e9e8e3; --surface:#ffffff; --surface-2:#f9f9f7; --ink:#0b0b0b; --ink-2:#52514e;
    --mute:#898781; --rule:#e1e0d9; --track:#ecebe6; --good:#006300; --bad:#e34948; --flat:#898781; --accent:#2a78d6;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  html, body { background:var(--page); color:var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif; }
  body { scroll-snap-type:y mandatory; overflow-y:scroll; height:100vh; }
  .slide { height:100vh; display:flex; align-items:center; justify-content:center; scroll-snap-align:start; padding:1vh 0; }
  .frame { width:min(98vw, 174vh); aspect-ratio:16/9; background:var(--surface); border:1px solid var(--rule); box-shadow:0 1px 3px rgba(0,0,0,.06);
    border-radius:1.2cqw; container-type:inline-size; display:flex; flex-direction:column; padding:2.6cqw 3.2cqw 1.6cqw; overflow:hidden; }
  header { display:flex; justify-content:space-between; align-items:flex-end; border-bottom:1px solid var(--rule); padding-bottom:1.2cqw; }
  h1 { font-size:3.4cqw; font-weight:700; letter-spacing:-0.02em; }
  .sub { font-size:1.35cqw; color:var(--mute); margin-top:.3cqw; }
  .meta { text-align:right; } .wk { font-size:1.7cqw; font-weight:600; } .vs { font-size:1.15cqw; color:var(--mute); }
  main { flex:1; display:flex; flex-direction:column; justify-content:center; gap:1.6cqw; padding:1.6cqw 0; min-height:0; }
  footer { display:flex; justify-content:space-between; font-size:1cqw; color:var(--mute); border-top:1px solid var(--rule); padding-top:.8cqw; }
  .chip { display:inline-block; font-size:1.05cqw; font-weight:700; padding:.15cqw .55cqw; border-radius:.5cqw; white-space:nowrap; }
  .chip.up { color:var(--good); background:color-mix(in srgb, var(--good) 15%, transparent); }
  .chip.down { color:var(--bad); background:color-mix(in srgb, var(--bad) 15%, transparent); }
  .chip.flat, .chip.na { color:var(--flat); background:color-mix(in srgb, var(--flat) 15%, transparent); }
  .tag { display:inline-block; font-size:1.05cqw; font-weight:700; padding:.2cqw .7cqw; border-radius:.5cqw;
    color:var(--c); background:color-mix(in srgb, var(--c) 18%, transparent); text-transform:uppercase; letter-spacing:.04em; }
  .nodata { flex:1; display:flex; align-items:center; justify-content:center; text-align:center; font-size:2.6cqw; color:var(--mute);
    border:2px dashed var(--rule); border-radius:1cqw; padding:2cqw; min-height:8cqw; }
  .nd { color:var(--mute); font-size:1.2cqw; }
  table.score { width:100%; border-collapse:collapse; }
  table.score th, table.score td { padding:.85cqw 1cqw; border-bottom:1px solid var(--rule); text-align:right; }
  table.score thead th { font-size:1.2cqw; color:var(--mute); font-weight:600; }
  table.score th.lh { text-align:left; }
  table.score th.rowh { text-align:left; font-size:1.55cqw; font-weight:600; color:var(--ink-2); }
  table.score th.rowh small { display:block; font-size:.95cqw; color:var(--mute); font-weight:400; }
  table.score .v { font-size:2.5cqw; font-weight:700; line-height:1.1; }
  table.score td.total { background:var(--surface-2); }
  table.score.small th, table.score.small td { padding:.45cqw .9cqw; }
  table.score.small .v { font-size:1.5cqw; display:inline-block; margin-right:.5cqw; }
  table.score.small th.rowh { font-size:1.2cqw; }
  table.score.small .chip { font-size:.9cqw; }
  .tiles { display:grid; gap:1.1cqw; } .tiles.six { grid-template-columns:repeat(6,1fr); } .tiles.five { grid-template-columns:repeat(5,1fr); }
  .tile { background:var(--surface-2); border:1px solid var(--rule); border-radius:.9cqw; padding:1.1cqw 1.2cqw; }
  .tile.hero { border-color:var(--accent); }
  .tile-label { font-size:1.15cqw; color:var(--ink-2); font-weight:600; }
  .tile-value { font-size:3.2cqw; font-weight:800; letter-spacing:-0.02em; margin:.3cqw 0; }
  .tile-wow { display:flex; gap:.6cqw; align-items:center; flex-wrap:wrap; }
  .tile-prev { font-size:.95cqw; color:var(--mute); }
  .tile-sub { font-size:.9cqw; color:var(--mute); margin-top:.3cqw; }
  .half { flex:1; display:flex; flex-direction:column; justify-content:center; min-height:0; }
  .half-title { font-size:1.3cqw; color:var(--mute); font-weight:600; margin-bottom:.7cqw; text-transform:uppercase; letter-spacing:.05em; }
  .gcards { display:grid; grid-template-columns:repeat(3,1fr); gap:1.1cqw; }
  .gcard { background:var(--surface-2); border:1px solid var(--rule); border-radius:.9cqw; padding:1cqw 1.2cqw; }
  .gname { font-size:1.55cqw; font-weight:700; margin-bottom:.5cqw; display:flex; align-items:baseline; gap:.6cqw; }
  .gname .score { margin-left:auto; font-size:.95cqw; color:var(--mute); font-weight:500; }
  .rank-s { color:var(--accent); }
  .m { display:grid; grid-template-columns:1fr auto auto; gap:.6cqw; align-items:center; padding:.2cqw 0; font-size:1.15cqw; }
  .ml { color:var(--ink-2); } .mv { font-weight:700; font-size:1.35cqw; }
  .wins { display:grid; grid-template-columns:repeat(3,1fr); gap:1.6cqw; }
  .win { background:var(--surface-2); border:1px solid var(--rule); border-radius:1cqw; padding:1.1cqw; }
  .thumb { position:relative; aspect-ratio:4/3; border-radius:.7cqw; overflow:hidden; background:var(--page); }
  .thumb img { width:100%; height:100%; object-fit:cover; display:block; }
  .noimg { width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:var(--mute); font-size:1.2cqw; }
  .rank { position:absolute; top:.6cqw; left:.6cqw; background:rgba(0,0,0,.7); color:#fff; font-weight:800; font-size:1.4cqw; padding:.1cqw .6cqw; border-radius:.5cqw; }
  .win-meta { display:flex; align-items:center; gap:.7cqw; margin-top:.8cqw; } .prop { font-size:1.35cqw; font-weight:600; }
  .win-big { font-size:3.6cqw; font-weight:800; margin-top:.4cqw; line-height:1; }
  .win-label, .win-sub { font-size:1cqw; color:var(--mute); margin-top:.3cqw; }
  .win-wow { display:flex; gap:.6cqw; align-items:center; margin-top:.4cqw; }
  .url-table { min-height:0; }
  /* slide 1: Detail-Pack-style KPI cards */
  .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:1.4cqw; }
  .kpi { background:var(--surface-2); border:1px solid var(--rule); border-radius:1cqw; padding:1.8cqw 1.8cqw 1.6cqw; }
  .kpi-label { font-size:1.15cqw; text-transform:uppercase; letter-spacing:.07em; color:var(--mute); font-weight:600; }
  .kpi-value { font-size:5cqw; font-weight:750; letter-spacing:-0.02em; line-height:1.1; margin:.6cqw 0 .5cqw; }
  .kpi-wow { display:flex; gap:.6cqw; align-items:center; min-height:2cqw; }
  .kpi-chips { display:flex; flex-direction:column; gap:.6cqw; margin-top:1.4cqw; padding-top:1.2cqw; border-top:1px solid var(--rule); }
  .pchip { display:flex; align-items:center; gap:.7cqw; font-size:1.6cqw; }
  .pchip b { font-weight:700; }
  .ico { display:inline-flex; width:2cqw; height:2cqw; flex-shrink:0; } .ico svg { width:100%; height:100%; }
  h1 .ico { width:3.4cqw; height:3.4cqw; vertical-align:-0.4cqw; margin-left:.6cqw; }
  /* slide 2: platform-coded table */
  table.score th.ph { text-align:right; font-size:1.35cqw; color:var(--ink); border-bottom:.35cqw solid var(--c, var(--ink-2)); }
  table.score th.ph .ico { width:1.9cqw; height:1.9cqw; vertical-align:middle; margin-right:.5cqw; }
  table.score th.ph span { vertical-align:middle; font-weight:700; }
  table.score th.ph.tot { --c: var(--ink-2); }
  table.score td.cell:not(.total) { background:color-mix(in srgb, var(--c) 6%, transparent); }
  table.score .bar { height:.45cqw; background:var(--track); border-radius:.3cqw; margin:.35cqw 0 .45cqw auto; width:70%; overflow:hidden; }
  table.score .bar i { display:block; height:100%; background:var(--c); border-radius:.3cqw; }
  .more { font-size:1cqw; color:var(--mute); margin-top:.4cqw; }
  @media print {
    @page { size: 13.333in 7.5in; margin:0; }
    body { height:auto; overflow:visible; }
    .slide { height:7.5in; padding:0; page-break-after:always; break-after:page; }
    .frame { width:13.333in; border:none; border-radius:0; }
    * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  }
</style>
</head>
<body>
{{SLIDES}}
<script>
  // ←/→, PageUp/PageDown, space: move between slides.
  document.addEventListener('keydown', function (e) {
    var s = Array.prototype.slice.call(document.querySelectorAll('.slide'));
    var y = window.scrollY || document.body.scrollTop, h = window.innerHeight;
    var idx = Math.round((document.body.scrollTop || y) / h);
    if (['ArrowRight','ArrowDown','PageDown',' '].indexOf(e.key) >= 0) idx = Math.min(idx + 1, s.length - 1);
    else if (['ArrowLeft','ArrowUp','PageUp'].indexOf(e.key) >= 0) idx = Math.max(idx - 1, 0);
    else return;
    e.preventDefault(); s[idx].scrollIntoView({ behavior: 'smooth' });
  });
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_file")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = ap.parse_args()
    page, out_path, log = build(Path(args.data_file).resolve(), Path(args.config).resolve())
    out_path.write_text(page)
    for line in log:
        print(f"[brief] {line}")
    print(f"[brief] wrote {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
