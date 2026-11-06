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
missing renders "N/A" instead of failing the build.
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
        return "N/A"
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
        return '<span class="chip na">N/A</span>'
    if prev is None:
        return '<span class="chip na">N/A</span>'
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


def no_data(msg="N/A"):
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


def top_channels(ctx):
    """{label: (winners list, value)} for views / engagement / followers. Ties keep every winner."""
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    tcfg = cfg.get("top_channels", {})
    m = scoreboard_metrics(ctx["data"], platforms, cfg.get("scoreboard", {})) or {}
    out = []
    for label, key in tcfg.get("categories", [["Views", "impressions"], ["Engagement", "_interactions"], ["Followers", "followers_gained"]]):
        vals = {c: m.get(key, {}).get(c) for c in platforms}
        vals = {c: v for c, v in vals.items() if v is not None}
        if not vals:
            out.append((label, [], None))
            continue
        best = max(vals.values())
        out.append((label, [c for c, v in vals.items() if v == best], best))
    return out


def top_channels_html(ctx):
    pills = []
    for label, winners, _ in top_channels(ctx):
        if not winners:
            who = '<span class="nd">N/A</span>'
        elif len(winners) == 1:
            who = f'{icon(winners[0])}<b>{esc(winners[0])}</b>'
        else:
            who = "".join(icon(w) for w in winners) + f'<b>Even: {esc(" & ".join(winners))}</b>'
        pills.append(f'<span class="tc"><span class="tc-l">{esc(label)}</span>{who}</span>')
    return f'<div class="tcs">{"".join(pills)}</div>'


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
    """Small-multiple vertical bar charts, one panel per KPI, one bar per platform."""
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    cur = scoreboard_metrics(ctx["data"], platforms, cfg.get("scoreboard", {}))
    prev = scoreboard_metrics(ctx["prev"], platforms, cfg.get("scoreboard", {}))
    if cur is None:
        return no_data()
    panels_def = [
        ("Reach", "reach", "int", True),
        ("Impressions", "impressions", "int", True),
        ("Engagement rate", "er", "pct", True),
        ("Followers gained", "followers_gained", "signed", True),
        ("Posts published", "posts", "int", False),
    ]
    panels, any_value = [], False
    for label, key, kind, show_wow in panels_def:
        vals = {c: cur[key].get(c) for c in platforms}
        tot, tot_p = cur[key].get("Total"), (prev[key].get("Total") if prev else None)
        if all(v is None for v in vals.values()):
            panels.append(f'<div class="panel"><div class="p-title">{esc(label)}</div>'
                          f'<div class="p-nodata">N/A</div></div>')
            continue
        any_value = True
        peak = max([abs(v) for v in vals.values() if v is not None] + [0]) or 1
        bars = []
        for c in platforms:
            v = vals[c]
            p = prev[key].get(c) if prev else None
            h = (max(v, 0) / peak * 100) if v is not None else 0
            chip = wow(v, p) if (show_wow and v is not None) else ""
            bars.append(
                f'<div class="col" style="--c:{CHANNEL_COLORS[c]}">'
                f'<div class="val">{fmt(v, kind) if v is not None else "N/A"}</div>'
                f'<div class="track"><div class="fill" style="height:{h:.1f}%"></div></div>'
                f'<div class="ctag">{icon(c)}</div><div class="cwow">{chip}</div></div>'
            )
        tot_wow = wow(tot, tot_p) if show_wow else ""
        panels.append(
            f'<div class="panel"><div class="p-title">{esc(label)}</div>'
            f'<div class="p-total">Total <b>{fmt(tot, kind) if tot is not None else "N/A"}</b> {tot_wow}</div>'
            f'<div class="bars">{"".join(bars)}</div></div>'
        )
    if not any_value:
        return no_data()
    legend = "".join(f'<span class="lg">{icon(c)}{esc(c)}</span>' for c in platforms)
    return f'<div class="legend">{legend}</div><div class="panels">{"".join(panels)}</div>'


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

    # Only posts from the week's top properties overall (0 = all properties).
    k = int(wcfg.get("top_properties", 0) or 0)
    allowed = None
    if k and isinstance(data.get("properties"), list):
        pm = wcfg.get("property_rank_metric", "engagement")
        ranked_props = sorted(data["properties"], key=lambda p: num((p.get(pm) or {}).get("current")) or 0, reverse=True)
        allowed = {p.get("name") for p in ranked_props[:k]}

    ranked = []
    for p in posts:
        if p.get("platform") not in platforms:
            continue
        if allowed is not None and p.get("property") not in allowed:
            continue
        numer = num(p.get(sort_m))
        den, den_used = num(p.get(den_m)), den_m
        if not den and fb_m:
            den, den_used = num(p.get(fb_m)), fb_m
        if numer is None or not den or den < min_den:
            continue
        ranked.append(dict(p, _rate=numer / den, _den_used=den_used, _numer=numer, _den=den))
    ranked.sort(key=lambda r: (r["_rate"], num(r.get(tie)) or 0), reverse=True)

    # Always top_n (3); up to max_n (5) only if the extra post is close enough to #3.
    n, mx = int(wcfg.get("top_n", 3)), int(wcfg.get("max_n", 5))
    ratio = float(wcfg.get("extra_if_rate_at_least_ratio_of_last", 0.85))
    top = ranked[:n]
    for r in ranked[n:mx]:
        if top and r["_rate"] >= top[-1]["_rate"] * ratio and r["_rate"] >= top[n - 1]["_rate"] * ratio:
            top.append(r)
        else:
            break
    return top


def slide_wins(ctx):
    cfg = ctx["config"]
    platforms = cfg["social_platforms"]
    top = rank_posts(ctx["data"], cfg, platforms)
    if not top:
        return no_data("N/A — no post-level metrics (social_posts) in this week's data file")
    prev_top = rank_posts(ctx["prev"], cfg, platforms) or []
    sort_m = cfg.get("social_wins", {}).get("sort_metric", "interactions")
    cards = []
    for i, p in enumerate(top):
        ptype = p.get("type") or "Post"
        context = p.get("context") or (p.get("caption") or "")[:110]
        # Screenshot when one loads (local copy first, then Metricool's image URL);
        # the placeholder (type + context) sits underneath and shows if it doesn't.
        thumb = p.get("thumbnail") or p.get("image_url")
        visual = (f'<div class="ph-box"><div class="ph-type">{esc(ptype)}</div>'
                  f'<div class="ph-ctx">{esc(context) or "No caption"}</div>'
                  f'<div class="ph-date">{esc(p.get("date", ""))}</div></div>')
        if thumb:
            visual += (f'<img class="shot" src="{esc(thumb)}" alt="{esc(context)}" referrerpolicy="no-referrer" '
                       f'onerror="this.remove()">')
        if p.get("url"):
            visual = f'<a href="{esc(p["url"])}" target="_blank" rel="noopener">{visual}</a>'
        prev_rate = prev_top[i]["_rate"] if i < len(prev_top) else None
        wow_html = (f'<div class="win-wow">{wow(p["_rate"], prev_rate)}<span class="tile-prev">vs last wk #{i + 1}</span></div>'
                    if prev_rate is not None else "")
        why = f'<div class="why"><b>Why it likely worked:</b> {esc(p["why"])}</div>' if p.get("why") else ""
        cards.append(
            '<div class="win">'
            f'<div class="thumb">{visual}<span class="rank">#{i + 1}</span><span class="ptype">{esc(ptype)}</span></div>'
            f'<div class="win-meta">{icon(p.get("platform"))}<span class="prop">{esc(p.get("property", "—"))}</span></div>'
            f'<div class="win-big">{fmt(p["_rate"], "pct")} <span class="win-label">engagement rate</span></div>'
            f'{wow_html}'
            f'<div class="win-sub">{fmt(p["_numer"])} {esc(sort_m)} · {fmt(p["_den"])} {esc(p["_den_used"])}</div>'
            f'{why}</div>'
        )
    return f'<div class="wins n{len(cards)}">{"".join(cards)}</div>'


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

def link_source(data, src, ucfg):
    """Normalized {clicks, leads, rows{name:(clicks, leads)}, origin} for one organic-link source, or None.
    Prefers the GA4 organic_links block; falls back to the Detail Pack's legacy url_tracking sections."""
    if not data:
        return None
    cf, lf = ucfg.get("clicks_field", "sessions"), ucfg.get("leads_field", "key_events")
    ol = ((data.get(ucfg.get("organic_links_key", "organic_links")) or {}).get("sources") or {}).get(src["key"])
    if isinstance(ol, dict):
        rows = {r.get("name"): (num(r.get(cf)) or 0, num(r.get(lf)) or 0) for r in ol.get("by_property", [])}
        return {"clicks": num(ol.get(cf)), "leads": num(ol.get(lf)), "rows": rows, "origin": "organic_links",
                "clicks_prev": None, "leads_prev": None}
    sec = data.get(src.get("legacy_section") or "")
    if not isinstance(sec, dict):
        return None
    llf = src.get("legacy_leads_field", lf)

    def pair(field):
        m = sec.get(field)
        if not isinstance(m, dict) or num(m.get("current")) is None:
            return None, None
        d = num(m.get("delta"))
        return m["current"], (m["current"] - d if d is not None else None)

    c, cp = pair(cf)
    l, lp = pair(llf)
    rows = {r.get("name"): (num(r.get(cf)) or 0, num(r.get(llf)) or 0) for r in sec.get("by_property", [])}
    return {"clicks": c, "leads": l, "rows": rows, "origin": "legacy", "clicks_prev": cp, "leads_prev": lp}


def link_sources(ctx):
    ucfg = ctx["config"].get("url_tracking", {})
    out = []
    for src in ucfg.get("sources", []):
        cur = link_source(ctx["data"], src, ucfg)
        if cur and cur["origin"] == "organic_links":
            prev = link_source(ctx["prev"], src, ucfg)
            if prev and prev["origin"] == "organic_links":   # only a real prior GA4 week counts
                cur["clicks_prev"], cur["leads_prev"] = prev["clicks"], prev["leads"]
        out.append((src, cur))
    return out


def source_badge(src):
    if src.get("icon") in CHANNEL_ICONS:
        return f'<span class="sb">{icon(src["icon"])}<b>{esc(src["label"])}</b></span>'
    return (f'<span class="sb"><span class="sb-dot" style="background:{esc(src.get("color", "#898781"))}">'
            f'{esc(src.get("short", "")[:1])}</span><b>{esc(src["label"])}</b></span>')


def slide_url(ctx):
    srcs = link_sources(ctx)
    if not any(cur for _, cur in srcs):
        return no_data()
    cards, leads, leads_p, labels = [], [], [], []
    for src, cur in srcs:
        color = src.get("color") or CHANNEL_COLORS.get(src.get("icon"), "#898781")
        if cur is None:
            body = '<div class="lc-na">N/A</div>'
        else:
            body = (
                f'<div class="lc-row"><span class="lc-l">Clicks</span><span class="lc-v">{fmt(cur["clicks"])}</span>'
                f'{wow(cur["clicks"], cur["clicks_prev"])}</div>'
                f'<div class="lc-row"><span class="lc-l">Leads</span><span class="lc-v">{fmt(cur["leads"])}</span>'
                f'{wow(cur["leads"], cur["leads_prev"])}</div>'
            )
            leads.append(cur["leads"])
            leads_p.append(cur["leads_prev"])
            labels.append(src.get("short", src["label"]))
        cards.append(f'<div class="lcard" style="--c:{esc(color)}">{source_badge(src)}{body}</div>')
    tot = sum(v for v in leads if v is not None) if leads else None
    tot_p = sum(leads_p) if leads_p and all(v is not None for v in leads_p) else None
    hero = (f'<div class="lhero"><div class="tile-label">Total organic leads</div>'
            f'<div class="lhero-v">{fmt(tot)}</div><div class="tile-wow">{wow(tot, tot_p)}'
            f'<span class="tile-prev">last wk {fmt(tot_p) if tot_p is not None else "N/A"}</span></div>'
            f'<div class="tile-sub">{esc(" + ".join(labels))} · leads = GA4 key events · clicks = sessions</div></div>')
    window = (ctx["data"].get(ctx["config"].get("url_tracking", {}).get("organic_links_key", "organic_links")) or {}).get("window_label")
    note = f'<div class="more">GA4 window: {esc(window)}</div>' if window else ""
    return f'<div class="lcards">{"".join(cards)}</div>{hero}{note}'


def slide_url_breakdown(ctx):
    srcs = link_sources(ctx)
    if not any(cur for _, cur in srcs):
        return no_data()
    names = []
    for p in ctx["data"].get("properties", []) or []:
        names.append(p.get("name"))
    for _, cur in srcs:
        for n in (cur or {}).get("rows", {}):
            if n not in names:
                names.append(n)

    def val(cur, n, i):
        if cur is None:
            return None
        return cur["rows"].get(n, (0, 0))[i]

    def total(n):
        l = sum(val(c, n, 1) or 0 for _, c in srcs)
        k = sum(val(c, n, 0) or 0 for _, c in srcs)
        return l, k

    names.sort(key=total, reverse=True)
    g_head = "".join(
        f'<th colspan="2" class="gh" style="--c:{esc(src.get("color") or CHANNEL_COLORS.get(src.get("icon"), "#898781"))}">{source_badge(src)}</th>'
        for src, _ in srcs
    )
    s_head = "".join('<th class="shc">Clicks</th><th class="shl">Leads</th>' for _ in srcs)
    rows = []
    for n in names:
        l, k = total(n)
        cells = []
        for _, cur in srcs:
            for i in (0, 1):
                v = val(cur, n, i)
                cls = "z" if v == 0 else ""
                cells.append(f'<td class="{cls} {"lead" if i else ""}">{"N/A" if v is None else fmt(v)}</td>')
        rows.append(f'<tr><th class="rowh">{esc(n)}</th>{"".join(cells)}'
                    f'<td class="tl">{fmt(l)}</td></tr>')
    return (f'<table class="bd"><thead><tr><th></th>{g_head}<th class="gh tot">Total</th></tr>'
            f'<tr><th class="lh">Property</th>{s_head}<th class="shl">Leads</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

SLIDES = [
    ("Top channels", top_channels_html, slide_overview),
    ("Social Scoreboard", "By platform · this week vs last week", slide_scoreboard),
    ("Google My Business", "Portfolio-wide + top properties", slide_gmb),
    ("Organic URL Tracking", "FB Groups · Google Business · Facebook · Instagram — tracked links", slide_url),
    ("Organic URL Tracking — by property", "Clicks (sessions) and leads (key events) per source", slide_url_breakdown),
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
        if callable(subtitle):
            try:
                sub_html = subtitle(ctx)
            except Exception as e:
                log.append(f"slide {i} subtitle: ERROR {e!r}")
                sub_html = esc("N/A")
        else:
            sub_html = esc(subtitle)
        try:
            body = fn(ctx)
        except Exception as e:  # a broken source must not fail the deck
            log.append(f"slide {i} ({title}): ERROR {e!r} -> rendered 'N/A'")
            traceback.print_exc(file=sys.stderr)
            body = no_data()
        nd = body.count("N/A")
        log.append(f"slide {i} ({title}): ok" + (f" ({nd} 'N/A' cell(s))" if nd else ""))
        window = ""
        if fn is slide_gmb and data.get("gbp_window_label"):
            window = f'GBP window {esc(data["gbp_window_label"])} vs {esc(data.get("gbp_prev_window_label", "—"))}'
        sections.append(
            f'<section class="slide" id="s{i}"><div class="frame">'
            f'<header><div><h1>{esc(title)}</h1><div class="sub">{sub_html}</div></div>'
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
  .wins { display:grid; grid-template-columns:repeat(3,1fr); gap:1.4cqw; }
  .wins.n4 { grid-template-columns:repeat(4,1fr); } .wins.n5 { grid-template-columns:repeat(5,1fr); gap:1cqw; }
  .ptype { position:absolute; top:.6cqw; right:.6cqw; background:rgba(255,255,255,.92); color:#0b0b0b; font-weight:700; font-size:1cqw; padding:.15cqw .55cqw; border-radius:.5cqw; }
  .ph-box { width:100%; height:100%; display:flex; flex-direction:column; justify-content:center; gap:.6cqw; padding:1.4cqw; background:var(--surface-2); border:2px dashed var(--rule); border-radius:.7cqw; }
  .ph-type { font-size:1.6cqw; font-weight:800; }
  .ph-ctx { font-size:1.15cqw; color:var(--ink-2); line-height:1.35; }
  .ph-date { font-size:.95cqw; color:var(--mute); }
  .why { font-size:1.05cqw; color:var(--ink-2); line-height:1.35; margin-top:.6cqw; padding-top:.6cqw; border-top:1px solid var(--rule); }
  .win-meta .ico { width:1.8cqw; height:1.8cqw; }
  .win { background:var(--surface-2); border:1px solid var(--rule); border-radius:1cqw; padding:1.1cqw; }
  .thumb { position:relative; aspect-ratio:1/1; border-radius:.7cqw; overflow:hidden; background:var(--page); }
  .thumb img { width:100%; height:100%; object-fit:cover; display:block; }
  .thumb img.shot { position:absolute; inset:0; }
  .thumb a { display:block; width:100%; height:100%; color:inherit; text-decoration:none; }
  .noimg { width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:var(--mute); font-size:1.2cqw; }
  .rank { position:absolute; top:.6cqw; left:.6cqw; background:rgba(0,0,0,.7); color:#fff; font-weight:800; font-size:1.4cqw; padding:.1cqw .6cqw; border-radius:.5cqw; }
  .win-meta { display:flex; align-items:center; gap:.7cqw; margin-top:.8cqw; } .prop { font-size:1.35cqw; font-weight:600; }
  .win-big { font-size:3cqw; font-weight:800; margin-top:.4cqw; line-height:1; }
  .win-big .win-label { font-size:1cqw; font-weight:500; }
  .win-label, .win-sub { font-size:1cqw; color:var(--mute); margin-top:.3cqw; }
  .win-wow { display:flex; gap:.6cqw; align-items:center; margin-top:.4cqw; }
  .url-table { min-height:0; }
  .lcards { display:grid; grid-template-columns:repeat(4,1fr); gap:1.2cqw; }
  .lcard { background:var(--surface-2); border:1px solid var(--rule); border-top:.4cqw solid var(--c); border-radius:1cqw; padding:1.2cqw 1.4cqw; }
  .sb { display:inline-flex; align-items:center; gap:.6cqw; font-size:1.4cqw; }
  .sb .ico { width:2cqw; height:2cqw; }
  .sb-dot { width:2cqw; height:2cqw; border-radius:50%; color:#fff; font-weight:800; font-size:1.1cqw; display:inline-flex; align-items:center; justify-content:center; }
  .lc-row { display:grid; grid-template-columns:auto 1fr auto; align-items:baseline; gap:.8cqw; margin-top:1cqw; }
  .lc-l { font-size:1.1cqw; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); font-weight:600; }
  .lc-v { font-size:3cqw; font-weight:800; text-align:right; letter-spacing:-0.02em; }
  .lc-na { font-size:2.4cqw; color:var(--mute); margin-top:1.4cqw; }
  .lhero { background:var(--surface-2); border:1px solid var(--accent); border-radius:1cqw; padding:1.2cqw 1.6cqw; display:grid; grid-template-columns:auto auto 1fr; align-items:center; gap:2cqw; }
  .lhero .tile-label { font-size:1.5cqw; }
  .lhero-v { font-size:4.4cqw; font-weight:800; }
  .lhero .tile-sub { text-align:right; font-size:1.05cqw; }
  table.bd { width:100%; border-collapse:collapse; font-size:1.2cqw; }
  table.bd th, table.bd td { padding:.38cqw .7cqw; border-bottom:1px solid var(--rule); text-align:right; }
  table.bd th.gh { text-align:center; border-bottom:.35cqw solid var(--c, var(--ink-2)); padding-bottom:.5cqw; }
  table.bd th.gh .sb { font-size:1.15cqw; } table.bd th.gh .ico, table.bd th.gh .sb-dot { width:1.6cqw; height:1.6cqw; font-size:.9cqw; }
  table.bd th.gh.tot { --c: var(--ink-2); font-size:1.15cqw; }
  table.bd th.lh { text-align:left; color:var(--mute); font-weight:600; }
  table.bd th.shc, table.bd th.shl { font-size:.95cqw; color:var(--mute); font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
  table.bd th.shl { border-right:1px solid var(--rule); }
  table.bd td.lead { font-weight:750; border-right:1px solid var(--rule); }
  table.bd td.z { color:#c3c2b7; }
  table.bd th.rowh { text-align:left; font-weight:600; color:var(--ink); white-space:nowrap; }
  table.bd td.tl { font-weight:800; font-size:1.35cqw; background:var(--surface-2); }
  /* slide 1 header: top channels */
  .tcs { display:flex; gap:1cqw; margin-top:.8cqw; flex-wrap:wrap; }
  .tc { display:inline-flex; align-items:center; gap:.6cqw; background:var(--surface-2); border:1px solid var(--rule);
    border-radius:5cqw; padding:.45cqw 1.1cqw .45cqw .6cqw; font-size:1.45cqw; color:var(--ink); }
  .tc-l { font-size:1.05cqw; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); font-weight:600;
    background:var(--surface); border-radius:3cqw; padding:.15cqw .7cqw; }
  .tc .ico { width:2cqw; height:2cqw; margin-right:-.2cqw; }
  /* slide 2: small-multiple vertical bars */
  .legend { display:flex; gap:1.8cqw; justify-content:flex-end; font-size:1.2cqw; color:var(--ink-2); }
  .lg { display:inline-flex; align-items:center; gap:.5cqw; font-weight:600; }
  .lg .ico { width:1.6cqw; height:1.6cqw; }
  .panels { display:grid; grid-template-columns:repeat(5,1fr); gap:1.2cqw; flex:1; min-height:0; }
  .panel { background:var(--surface-2); border:1px solid var(--rule); border-radius:1cqw; padding:1.1cqw 1cqw .8cqw; display:flex; flex-direction:column; min-height:0; }
  .p-title { font-size:1.1cqw; text-transform:uppercase; letter-spacing:.06em; color:var(--mute); font-weight:700; }
  .p-total { font-size:1.15cqw; color:var(--ink-2); margin:.4cqw 0 .8cqw; display:flex; gap:.5cqw; align-items:center; flex-wrap:wrap; }
  .p-total b { color:var(--ink); font-size:1.6cqw; }
  .p-nodata { flex:1; display:flex; align-items:center; justify-content:center; color:var(--mute); font-size:1.6cqw; border:2px dashed var(--rule); border-radius:.8cqw; }
  .bars { flex:1; display:grid; grid-template-columns:repeat(3,1fr); gap:.7cqw; min-height:0; }
  .col { display:flex; flex-direction:column; align-items:center; min-height:0; }
  .val { font-size:1.45cqw; font-weight:750; margin-bottom:.3cqw; white-space:nowrap; }
  .track { flex:1; width:72%; display:flex; align-items:flex-end; border-bottom:2px solid var(--rule); min-height:4cqw; }
  .fill { width:100%; background:var(--c); border-radius:.5cqw .5cqw 0 0; min-height:2px; }
  .ctag { margin-top:.5cqw; } .ctag .ico { width:1.8cqw; height:1.8cqw; }
  .cwow { margin-top:.3cqw; min-height:1.6cqw; } .cwow .chip { font-size:.85cqw; padding:.1cqw .35cqw; }
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
