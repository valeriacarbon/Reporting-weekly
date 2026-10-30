#!/usr/bin/env python3
"""Build the Organic Brief (brief.html) on top of the weekly Detail Pack.

The weekly dashboard (index.html, built by build_report.py) stays the Detail
Pack. This script reads the same data/week-*.json file, plus the previous
weeks' files and data/brief-inputs.json, and writes a 5-slide presentation:

  1. Scoreboard          8 tiles, each on/off track
  2. Wins and losses     3 wins (each with a why), 3 losses (each with a next step)
  3. Reviews             Opiniion standing + this week's new reviews
  4. Priority properties ramp-up, under-floor rating, watchlist
  5. Actions             next steps with owner and due, last week, asks

Usage: python3 scripts/build_brief.py data/week-YYYY-MM-DD.json
Anything the data cannot answer prints as a [bracketed placeholder].
"""

import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUTS_PATH = REPO_ROOT / "data" / "brief-inputs.json"
OUT_PATH = REPO_ROOT / "brief.html"

INK = "#18214A"
MUTE = "#6B7385"
BODY = "#4A5366"
BLUE = "#2F5BD3"
GOOD = "#17734A"
BAD = "#B42318"
WARN = "#8A5A00"
STALE = "#8A8F9C"


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    if n is None:
        return "—"
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}"
    return f"{int(round(n)):,}"


def pct(cur, prev):
    if not prev:
        return None
    return round((cur - prev) / prev * 100)


def span_label(label):
    """'Oct 22 – 29, 2026' -> 'Oct 22 to 29'."""
    label = re.sub(r",\s*\d{4}", "", label)
    return re.sub(r"\s*[–-]\s*", " to ", label).strip()


def join_names(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def is_carried(section):
    return "carried forward" in (section or {}).get("note", "").lower()


# ---------------------------------------------------------------- data access

def load_weeks(data_path):
    """Return (current, [previous files newest-first, up to 4])."""
    current = json.loads(data_path.read_text())
    files = sorted(data_path.parent.glob("week-*.json"))
    older = [f for f in files if f.name < data_path.name][-4:]
    previous = [json.loads(f.read_text()) for f in reversed(older)]
    return current, previous


def by_channel(rows):
    return {r["channel"]: r["current"] for r in rows or []}


def gb_actions(d):
    g = d["google_business"]
    keys = ("website_clicks", "phone_clicks", "directions_clicks")
    cur = sum(g[k]["current"] for k in keys)
    delta = sum(g[k]["delta"] for k in keys)
    return cur, cur - delta


def per_1k(eng, views):
    return round(eng / views * 1000, 1) if views else 0.0


def property_rows(d, inputs):
    gbp = {p["name"]: p for p in d.get("gbp_by_property", [])}
    gmb = {p["name"]: p for p in d.get("gmb_url_tracking", {}).get("by_property", [])}
    ratings = {r["name"]: r for r in inputs["ratings"]["by_property"]}
    rows = []
    for p in d["properties"]:
        g = gbp.get(p["name"])
        u = gmb.get(p["name"])
        r = ratings.get(p["name"])
        rows.append({
            "name": p["name"],
            "posts": p["posts"]["current"],
            "views": p["views"]["current"],
            "top_channel": p.get("top_channel"),
            "gb_actions": (g["website_clicks"] + g["phone_clicks"] + g["directions_clicks"]) if g else None,
            "site_visits": u["sessions"] if u else None,
            "key_events": u["key_events"] if u else None,
            "rating": r["rating"] if r else None,
        })
    return rows


# ---------------------------------------------------------------- html pieces

def slide(sid, inner, notes, footer):
    return (
        f'<section class="slide" id="{sid}">\n{inner}\n'
        f'<p class="footer">{esc(footer)}</p>\n'
        f'<aside class="notes">{esc(notes)}</aside>\n</section>'
    )


def tile(label, value, status, sub):
    color = {"on": GOOD, "off": BAD, "stale": STALE}[status]
    word = {"on": "On track.", "off": "Off track.", "stale": "No new data."}[status]
    return (
        '<div class="tile">'
        f'<div class="tile-bar" style="background:{color}"></div>'
        f'<p class="tile-label">{esc(label)}</p>'
        f'<p class="tile-value">{esc(value)}</p>'
        f'<p class="tile-sub"><span style="color:{color}"><b>{word}</b></span> {esc(sub)}</p>'
        '</div>'
    )


def item(head_html, foot, foot_is_placeholder=False):
    return (
        '<div class="item">'
        f'<p class="item-head">{head_html}</p>'
        f'<p class="item-foot{" ph" if foot_is_placeholder else ""}">{esc(foot)}</p>'
        '</div>'
    )


def td(value, color=None, bold=False, align=None):
    style = []
    if color:
        style.append(f"color:{color}")
    if align:
        style.append(f"text-align:{align}")
    s = f' style="{";".join(style)}"' if style else ""
    v = esc(value)
    return f"<td{s}>{'<b>' + v + '</b>' if bold else v}</td>"


def rating_color(r, floor):
    if r is None or r >= floor:
        return None
    return WARN if r >= 3.5 else BAD


# ---------------------------------------------------------------- slides

def build_scoreboard(d, prev, inputs, ctx):
    eng = by_channel(d["engagement_by_channel"])
    views = by_channel(d["views_by_channel"])
    targets = inputs["targets"]

    gba_cur, gba_prev = gba = gb_actions(d)
    gba_pct = pct(gba_cur, gba_prev)
    gbp_win = ctx["gbp_win"]

    gmb = d.get("gmb_url_tracking", {})
    gmb_stale = is_carried(gmb)
    visits = gmb.get("sessions", {}).get("current")
    visits_prev = visits - gmb["sessions"]["delta"] if visits is not None else None
    kev = gmb.get("key_events", {}).get("current")
    kev_rows = [p for p in gmb.get("by_property", []) if p.get("key_events")]
    kev_top = max(kev_rows, key=lambda p: p["key_events"]) if kev_rows else None

    ut = d.get("url_tracking", {})
    fg = d["facebook_groups"]
    fg_posts = fg.get("groups_and_posts", {}).get("posts", {}).get("current", 0)
    fg_int = fg.get("interactions", {}).get("current", 0)
    tours = ut.get("tours", {}).get("current", 0)

    ig_rate = per_1k(eng.get("Instagram", 0), views.get("Instagram", 0))
    tt_rate = per_1k(eng.get("TikTok", 0), views.get("TikTok", 0))

    posts = d["kpis"]["posts"]["current"]
    avg_src = [p["kpis"]["posts"]["current"] for p in prev]
    posts_avg = round(sum(avg_src) / len(avg_src)) if avg_src else None
    last_posts = posts - d["kpis"]["posts"]["delta"]

    rows = ctx["rows"]
    ramp = [r for r in rows if r["name"] in inputs["ramp_up"]]
    ramp_posted = [r for r in ramp if r["posts"] > 0]
    ramp_missing = [r["name"] for r in ramp if r["posts"] == 0]

    floor = targets["rating_floor"]
    low = sorted([r for r in inputs["ratings"]["by_property"] if r["rating"] < floor], key=lambda r: r["rating"])

    tiles = []
    if gba_pct is None:
        sub = gbp_win
    else:
        sub = f"{'Up' if gba_pct >= 0 else 'Down'} {abs(gba_pct)}% · {gbp_win}"
    tiles.append(tile("Google Business actions", fmt(gba_cur), "on" if gba_cur >= gba_prev else "off", sub))
    if gmb_stale:
        tiles.append(tile("Site visits from Google", fmt(visits), "stale", "No new GA4 export"))
        tiles.append(tile("Key events from Google", fmt(kev), "stale", "No new GA4 export"))
    else:
        tiles.append(tile("Site visits from Google", fmt(visits), "on" if visits >= visits_prev else "off",
                          f"Last reading {fmt(visits_prev)}"))
        tiles.append(tile("Key events from Google", fmt(kev), "on" if kev else "off",
                          f"{kev_top['name']} drove {kev_top['key_events']}" if kev_top else "None this week"))
    fg_sub = f"{fg_posts} posts, {fg_int} interaction{'' if fg_int == 1 else 's'}"
    if is_carried(ut):
        tiles.append(tile("Tours from FB groups", fmt(tours), "stale", f"No new GA4 export · {fg_sub}"))
    else:
        tiles.append(tile("Tours from FB groups", fmt(tours), "on" if tours > 0 else "off", fg_sub))
    tiles.append(tile("Instagram engagement", fmt(ig_rate),
                      "on" if ig_rate >= targets["ig_engagement_per_1k_views"] else "off",
                      f"Per 1k views · TikTok {fmt(tt_rate)}"))
    if posts_avg is not None:
        tiles.append(tile("Posts published", fmt(posts), "on" if posts >= posts_avg else "off",
                          f"4-wk avg {posts_avg} · last wk {last_posts}"))
    else:
        tiles.append(tile("Posts published", fmt(posts), "on" if posts >= last_posts else "off",
                          f"Last wk {last_posts}"))
    tiles.append(tile("Ramp-up coverage", f"{len(ramp_posted)} of {len(ramp)}",
                      "on" if not ramp_missing else "off",
                      "All posted this week" if not ramp_missing else f"No posts: {join_names(ramp_missing)}"))
    tiles.append(tile(f"Under {floor:.1f} stars", str(len(low)), "on" if not low else "off",
                      " · ".join(f"{short(r['name'])} {r['rating']}" for r in low[:2]) or "None"))

    fb_ig = eng.get("Facebook", 0) + eng.get("Instagram", 0)
    others = sum(v for k, v in eng.items() if k != "Google Business")
    if eng.get("Google Business", 0) > others:
        verdict = (f"Google Business is doing the converting. Facebook and Instagram drew "
                   f"{fmt(fb_ig)} interaction{'' if fb_ig == 1 else 's'} all week.")
    else:
        top = max(eng, key=eng.get)
        verdict = f"{top} led engagement with {fmt(eng[top])} interactions."

    health = [f"Google Business runs a week behind social ({gbp_win})."]
    if gmb_stale or is_carried(ut):
        health.append("No new GA4 export this week, so Google site visits, key events and FB group tours repeat last week's reading.")
    health.append("Facebook group posts are entered by hand.")
    health.append(f"Ratings are {inputs['ratings']['source']}, {inputs['ratings']['window_label']}.")
    health.append("The Detail Pack's Engagement and Views totals include Google Business, so the Brief splits by channel.")

    inner = (
        f'<p class="kicker">Organic Brief · Social {esc(ctx["social_win"])} · Google Business {esc(gbp_win)}</p>\n'
        f'<h2>{esc(verdict)}</h2>\n'
        f'<div class="tiles">{"".join(tiles)}</div>\n'
        f'<p class="health"><b>Data health:</b> {esc(" ".join(health))}</p>'
    )
    notes = (f"About 90 seconds. Verdict: {verdict} Read the red tiles, skip the green ones. "
             "Gray tiles had no new data this week. Slides 2 and 3 cover why and what is next.")
    ctx["scoreboard"] = {"ig_rate": ig_rate, "tt_rate": tt_rate, "fg_posts": fg_posts,
                         "fg_int": fg_int, "tours": tours, "low": low, "gba": gba,
                         "gmb_stale": gmb_stale, "visits": visits, "kev": kev, "kev_top": kev_top}
    return inner, notes


def short(name):
    return {"Residences at the Overlook": "Overlook", "Hills at Hoover": "Hills",
            "The Lamar Lofts": "Lamar", "Claxton Pointe & Pecan Ridge": "Claxton & Pecan",
            "The Landings at North Ingleside": "Landings"}.get(name, name)


def build_winslosses(d, prev, inputs, ctx, week):
    sb = ctx["scoreboard"]
    eng = by_channel(d["engagement_by_channel"])
    views = by_channel(d["views_by_channel"])
    rows = ctx["rows"]
    ramp = set(inputs["ramp_up"])
    kpis = d["kpis"]

    gba_cur, gba_prev = sb["gba"]
    gba_pct = pct(gba_cur, gba_prev)
    gb_rank = sorted([r for r in rows if r["gb_actions"] is not None], key=lambda r: -r["gb_actions"])[:2]
    views_top = max(rows, key=lambda r: r["views"])
    ig_fol = next((c for c in d["followers_by_channel"] if c["channel"] == "Instagram"), None)

    wins, losses = [], []
    # (key, short label for the headline, html head, default foot)
    if gba_cur >= gba_prev:
        lead = " and ".join(f"{esc(r['name'])} {fmt(r['gb_actions'])}" for r in gb_rank)
        both = ", both ramp-up" if len(gb_rank) == 2 and all(r["name"] in ramp for r in gb_rank) else ""
        change = f"up {gba_pct}% to" if gba_pct else "held at"
        wins.append(("gb_actions", "Google Business",
                     f"<b>Google Business actions {change} {fmt(gba_cur)}.</b> {lead} led{both}."))
    else:
        losses.append(("gb_actions", "Google Business",
                       f"<b>Google Business actions down {abs(gba_pct)}% to {fmt(gba_cur)}.</b>",
                       "Next: [what to change on the Google posts]"))
    if not sb["gmb_stale"] and sb["kev"]:
        top = sb["kev_top"]
        wins.append(("google_site", "Google site traffic",
                     f"<b>Google sent {fmt(sb['visits'])} site visits and {fmt(sb['kev'])} key events.</b> "
                     f"{esc(top['name'])} drove {top['key_events']} of them."))
    wins.append(("top_views", short(views_top["name"]),
                 f"<b>{esc(views_top['name'])} led views at {fmt(views_top['views'])},</b> "
                 f"with {esc(views_top['top_channel'])} as its top channel."))
    if sb["tt_rate"] > sb["ig_rate"] and eng.get("TikTok"):
        wins.append(("tiktok", "TikTok",
                     f"<b>TikTok drew {fmt(eng['TikTok'])} interactions on {fmt(views.get('TikTok', 0))} views.</b> "
                     f"{fmt(sb['tt_rate'])} per 1,000 views."))
    if kpis["followers"]["delta"] > 0:
        wins.append(("followers", "Follower growth",
                     f"<b>Followers up {fmt(kpis['followers']['delta'])} to {fmt(kpis['followers']['current'])}.</b>"))

    if sb["ig_rate"] < inputs["targets"]["ig_engagement_per_1k_views"]:
        if ig_fol is None:
            fol = ""
        elif ig_fol["delta"] == 0:
            fol = f" Followers flat at {fmt(ig_fol['current'])}."
        else:
            fol = f" Followers {'up' if ig_fol['delta'] > 0 else 'down'} {abs(ig_fol['delta'])} to {fmt(ig_fol['current'])}."
        ig_eng = eng.get("Instagram", 0)
        losses.append(("instagram", "Instagram",
                       f"<b>Instagram: {fmt(ig_eng)} interaction{'' if ig_eng == 1 else 's'} on "
                       f"{fmt(views.get('Instagram', 0))} views.</b>{fol}",
                       "Next: re-cut the top TikToks as Reels on 3 properties"))
    if sb["tours"] == 0:
        if sb["fg_posts"] == 0:
            losses.append(("fb_groups", "Facebook groups",
                           "<b>Facebook groups: no posts this week, 0 tours.</b>",
                           "Next: confirm whether group posting resumes, or retire the channel"))
        else:
            losses.append(("fb_groups", "Facebook groups",
                           f"<b>Facebook groups: {sb['fg_posts']} posts, {sb['fg_int']} interaction"
                           f"{'' if sb['fg_int'] == 1 else 's'}, 0 tours.</b>",
                           "Next: 1-week test commenting on active searches"))
    one = [r["name"] for r in rows if r["posts"] == 1]
    none = [r["name"] for r in rows if r["posts"] == 0]
    if one or none:
        parts = []
        if one:
            parts.append(f"{esc(join_names(one))} got only 1 post.")
        if none:
            parts.append(f"{esc(join_names(none))} got none.")
        losses.append(("coverage", "Low-post properties", f"<b>{' '.join(parts)}</b>",
                       "Next: confirm their plan in the next calendar"))
        ctx["coverage_gaps"] = one + none
    if kpis["posts"]["delta"] < 0:
        losses.append(("posts", "Post volume",
                       f"<b>Posts down to {kpis['posts']['current']} from "
                       f"{kpis['posts']['current'] - kpis['posts']['delta']}.</b>",
                       "Next: [what slipped from the calendar]"))
    if kpis["views"]["delta"] < 0:
        prev_views = kpis["views"]["current"] - kpis["views"]["delta"]
        losses.append(("views", "Views",
                       f"<b>Views down {abs(pct(kpis['views']['current'], prev_views))}% to "
                       f"{fmt(kpis['views']['current'])}.</b>",
                       "Next: [which property or channel dropped]"))

    wins, losses = wins[:3], losses[:3]
    ctx["losses"] = losses
    why, nxt = week.get("why", {}), week.get("next", {})

    win_html = "".join(
        item(h, f"Why: {why[k]}" if k in why else "Why: [Val to confirm what changed]", k not in why)
        for k, _, h in wins)
    loss_html = "".join(
        item(h, f"Next: {nxt[k]}" if k in nxt else default, default.startswith("Next: ["))
        for k, _, h, default in losses)

    w_labels = [lab for _, lab, _ in wins][:2]
    l_labels = [lab for _, lab, _, _ in losses][:2]
    headline = []
    if w_labels:
        headline.append(f"{join_names(w_labels)} carried the week.")
    if l_labels:
        headline.append(f"{join_names(l_labels)} did not.")

    inner = (
        f'<h2>{esc(" ".join(headline))}</h2>\n'
        f'<p class="sub">Social {esc(ctx["social_win"])}. Google Business {esc(ctx["gbp_win"])}.</p>\n'
        '<div class="cols">'
        f'<div class="card flex1"><h3 style="color:{GOOD}">Wins</h3>{win_html}</div>'
        f'<div class="card flex1"><h3 style="color:{BAD}">Losses</h3>{loss_html}</div>'
        '</div>'
    )
    notes = ("About 2 minutes. Every win needs a why, so the team can repeat it. Every loss needs a next step. "
             f"Bracketed lines are for Val to fill in. Loss next steps go to {inputs['approver']} for a yes or no on slide 5.")
    return inner, notes


def build_reviews(d, inputs, ctx, week):
    rt = inputs["ratings"]
    floor = inputs["targets"]["rating_floor"]
    low = ctx["scoreboard"]["low"]
    best = sorted([r for r in rt["by_property"] if r["rating"] >= 4.5], key=lambda r: -r["rating"])[:2]

    trs = "".join(
        "<tr>" + td(r["name"], bold=True) + td(r["rating"], rating_color(r["rating"], floor), True)
        + td(fmt(r["reviews"])) + td(f"{r['negative_pct']}%" if r["negative_pct"] is not None else "—",
                                     rating_color(r["rating"], floor)) + "</tr>"
        for r in low)
    pf = rt["portfolio"]
    trs += ('<tr class="total">' + td("Portfolio", bold=True) + td(pf["rating"], bold=True)
            + td(fmt(pf["reviews"]), bold=True) + td(f"{pf['negative_pct']}%", bold=True) + "</tr>")

    tw = week.get("reviews_this_week")
    if tw:
        this_week = [
            f"{tw['new']} new reviews: {tw['positive']} positive, {tw['negative']} negative",
            f"Top complaint: {tw['top_complaint']}",
            f"Top praise: {tw['top_praise']}",
            f"{tw['awaiting_reply']} waiting for a reply",
        ]
        ph = ""
    else:
        this_week = ["[__] new reviews: [__] positive, [__] negative", "Top complaint: [theme]",
                     "Top praise: [theme]", "[__] waiting for a reply"]
        ph = " ph"
    tw_html = "".join(f'<p class="line{ph}">{esc(x)}</p>' for x in this_week)

    if best:
        b = best[0]
        best_txt = f"{b['name']} {b['rating']}"
        if b["reviews"]:
            best_txt += f" on {b['reviews']} reviews"
        if b["negative_pct"] == 0:
            best_txt += ", none negative"
        best_txt += "."
        if len(best) > 1:
            best_txt += f" {best[1]['name']} {best[1]['rating']}."
    else:
        best_txt = f"No property at 4.5 stars or above."

    if low:
        headline = (f"{len(low)} propert{'y sits' if len(low) == 1 else 'ies sit'} under {floor:.1f} stars. "
                    f"{low[0]['name']} is the outlier at {low[0]['rating']}.")
    else:
        headline = f"Every property is at or above {floor:.1f} stars."

    inner = (
        f'<h2>{esc(headline)}</h2>\n'
        f'<p class="sub">{esc(rt["source"])}, {esc(rt["window_label"])}. This week’s new reviews on the right.</p>\n'
        '<div class="cols">'
        '<div class="flex58"><table>'
        '<tr><th style="width:46%;text-align:left">Property</th><th style="width:18%">Rating</th>'
        '<th style="width:18%">Reviews</th><th style="width:18%">Negative</th></tr>'
        f'{trs}</table></div>'
        '<div class="flex42 stack">'
        f'<div class="card"><h3 style="color:{BLUE}">This week</h3>{tw_html}</div>'
        f'<div class="card"><h3 style="color:{GOOD}">Best rated</h3><p class="line">{esc(best_txt)}</p></div>'
        '</div></div>'
    )
    notes = (f"About 90 seconds. Weekly view {inputs['approver']} asked for: new positive and negative reviews "
             "and the main theme of each. The table is the 12-month standing. Low ratings are usually on-site "
             "issues, so the ask is to raise them with the site teams.")
    return inner, notes


def build_priority(d, inputs, ctx, week):
    floor = inputs["targets"]["rating_floor"]
    rows = ctx["rows"]
    ramp = inputs["ramp_up"]
    pri_names = list(dict.fromkeys(
        ramp + inputs.get("watchlist", []) + [r["name"] for r in ctx["scoreboard"]["low"]]))
    pri = [r for r in rows if r["name"] in pri_names]
    pri.sort(key=lambda r: (r["name"] not in ramp, -(r["gb_actions"] or 0)))

    overrides = week.get("next_moves", {})
    stale = ctx["scoreboard"]["gmb_stale"]

    def next_move(r):
        if r["name"] in overrides:
            return overrides[r["name"]]
        if r["site_visits"] is not None and r["site_visits"] >= 50 and r["key_events"] == 0:
            return "Check the tour button on the page Google links to"
        if r["site_visits"] is not None and r["site_visits"] < 10:
            return "Check the Google link tracking"
        if r["rating"] is not None and r["rating"] < 3.0:
            return "Pair posts with replies to reviews"
        if r["posts"] == 0:
            return "Get posts back on the calendar"
        return "Keep the cadence"

    max_gba = max((r["gb_actions"] or 0) for r in pri) if pri else 0
    max_kev = max((r["key_events"] or 0) for r in pri) if pri else 0
    trs = ""
    flags = []
    for r in pri:
        mv = next_move(r)
        r["next_move"] = mv
        no_kev = r["site_visits"] is not None and r["site_visits"] >= 50 and r["key_events"] == 0
        low_sv = r["site_visits"] is not None and r["site_visits"] < 10
        if no_kev:
            flags.append(f"{r['name']}’s {r['site_visits']} site visits produced no key events.")
        elif low_sv:
            flags.append(f"{r['name']} sent only {r['site_visits']} site visits from Google.")
        trs += ("<tr>" + td(r["name"] + (" · ramp-up" if r["name"] in ramp else ""), bold=True)
                + td(r["posts"], BAD if r["posts"] == 0 else None)
                + td(fmt(r["gb_actions"]), GOOD if r["gb_actions"] and r["gb_actions"] == max_gba else None,
                     bool(r["gb_actions"] and r["gb_actions"] == max_gba))
                + td(fmt(r["site_visits"]), BAD if low_sv else None, low_sv)
                + td(fmt(r["key_events"]), BAD if no_kev else (GOOD if r["key_events"] and r["key_events"] == max_kev else None),
                     bool(no_kev or (r["key_events"] and r["key_events"] == max_kev)))
                + td(r["rating"] if r["rating"] is not None else "—", rating_color(r["rating"], floor))
                + td(mv, align="left") + "</tr>")
    ctx["priority"] = pri

    all_gb = [r for r in rows if r["gb_actions"] is not None]
    leader = max(all_gb, key=lambda r: r["gb_actions"]) if all_gb else None
    head = []
    if leader and leader["name"] in ramp:
        head.append("Ramp-up properties lead Google actions.")
    elif leader:
        head.append(f"{leader['name']} leads Google actions.")
    if flags:
        head.append(flags[0])

    visits_note = " Site visits repeat last week (no new GA4 export)." if stale else ""
    inner = (
        f'<h2>{esc(" ".join(head))}</h2>\n'
        f'<p class="sub">Posts {esc(ctx["social_win"])}. Google Business actions {esc(ctx["gbp_win"])}. '
        f'Ratings from Opiniion.{esc(visits_note)}</p>\n'
        '<table class="tight">'
        '<tr><th style="width:24%;text-align:left">Property</th><th style="width:8%">Posts</th>'
        '<th style="width:12%">Google actions</th><th style="width:11%">Site visits</th>'
        '<th style="width:11%">Key events</th><th style="width:8%">Rating</th>'
        '<th style="width:26%;text-align:left">Next move</th></tr>'
        f'{trs}</table>'
    )
    notes = ("About 2 minutes. Priority properties are the ramp-up properties, plus any property under "
             f"{floor:.1f} stars or on the watchlist. Every other property stays in the Detail Pack.")
    return inner, notes


def build_actions(inputs, ctx, week):
    steps = week.get("next_steps") or []
    drafted = not steps
    if drafted:
        seen = set()
        for key, _, _, foot in ctx["losses"]:
            text = foot.removeprefix("Next: ")
            if key == "coverage":
                text = f"confirm the plan for {join_names([short(n) for n in ctx['coverage_gaps']])} in the next calendar"
            if not text.startswith("["):
                steps.append({"action": text[0].upper() + text[1:], "owner": "Val", "due": "[date]"})
        for r in ctx["priority"]:
            if r["next_move"] != "Keep the cadence":
                key = r["next_move"]
                if key in seen:
                    continue
                seen.add(key)
                steps.append({"action": f"{r['name']}: {r['next_move'][0].lower()}{r['next_move'][1:]}", "owner": "Val", "due": "[date]"})
        steps = steps[:6]
    trs = "".join(
        "<tr>" + td(s["action"], align="left") + td(s["owner"], align="left")
        + td(s["due"], align="left") + "</tr>" for s in steps)

    lw = week.get("last_week")
    if lw:
        lw_txt = f"{lw['done']} of {lw['total']} done."
        if lw.get("open"):
            lw_txt += f" Still open: {join_names(lw['open'])}."
        lw_ph = ""
    else:
        lw_txt, lw_ph = "[__] of [__] done. Still open: [list the open items].", " ph"

    asks = week.get("asks") or []
    if not asks:
        keys = {k for k, _, _, _ in ctx["losses"]}
        if "fb_groups" in keys and ctx["scoreboard"]["fg_posts"] > 0:
            asks.append("Approve the 1-week Facebook groups test")
        elif "fb_groups" in keys:
            asks.append("Decide whether Facebook group posting continues")
        if ctx.get("coverage_gaps"):
            asks.append(f"Confirm the social plan for {join_names([short(n) for n in ctx['coverage_gaps']])}")
        very_low = [short(r["name"]) for r in ctx["scoreboard"]["low"] if r["rating"] < 3.5]
        if very_low:
            asks.append(f"Raise {join_names(very_low)} reviews with the site teams")
    asks_html = "".join(f"<li>{esc(a)}</li>" for a in asks) or "<li>None this week</li>"

    headline = f"{len(steps)} next step{'' if len(steps) == 1 else 's'} for next week"
    if asks:
        headline += f", {len(asks)} ask{'' if len(asks) == 1 else 's'}"
    draft_tag = ' <span class="draft">Draft: auto-built from slides 2 and 4</span>' if drafted else ""
    inner = (
        f'<h2>{esc(headline)}</h2>\n'
        '<div class="cols">'
        f'<div class="flex58 stack"><h3 style="color:{BLUE}">Next steps{draft_tag}</h3>'
        '<table class="tight"><tr><th style="width:62%;text-align:left">Action</th>'
        '<th style="width:20%;text-align:left">Owner</th><th style="width:18%;text-align:left">Due</th></tr>'
        f'{trs}</table></div>'
        '<div class="flex42 stack">'
        f'<div class="card"><h3>Last week</h3><p class="line{lw_ph}" style="color:{BODY}">{esc(lw_txt)}</p></div>'
        f'<div class="card"><h3 style="color:{BLUE}">Asks for {esc(inputs["approver"])}</h3><ol>{asks_html}</ol></div>'
        '</div></div>'
    )
    notes = ("About 1 minute. Read last week's actions as done or not done. Then the next steps, each with an "
             "owner and a date. Finish with the asks, and wait for a yes or no on each.")
    return inner, notes


# ---------------------------------------------------------------- page

CSS = """
:root { --bg:#F5F6F8; --ink:#18214A; }
html,body { margin:0; height:100%; background:#0F1426; }
body { font-family:'IBM Plex Sans', Arial, sans-serif; color:var(--ink); overflow:hidden; }
#stage { position:absolute; top:50%; left:50%; width:1920px; height:1080px; transform-origin:0 0; }
.slide { position:absolute; inset:0; box-sizing:border-box; background:var(--bg); color:var(--ink);
  padding:110px 128px 150px; display:none; flex-direction:column; gap:24px; }
.slide.active { display:flex; }
.slide p, .slide h2, .slide h3 { margin:0; }
h2 { font-size:52px; font-weight:600; line-height:1.15; }
h3 { font-size:32px; font-weight:600; display:flex; align-items:center; gap:16px; }
.kicker { font-size:24px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:#2F5BD3; }
.sub { font-size:24px; color:#6B7385; }
.tiles { display:grid; grid-template-columns:repeat(4,1fr); gap:24px; }
.tile { background:#fff; border-radius:12px; padding:20px 24px; display:flex; flex-direction:column; gap:8px; }
.tile-bar { width:56px; height:6px; border-radius:3px; }
.tile-label { font-size:24px; color:#6B7385; }
.tile-value { font-size:52px; font-weight:600; line-height:1.1; }
.tile-sub { font-size:22px; color:#4A5366; }
.health { font-size:22px; line-height:1.4; color:#4A5366; }
.cols { display:flex; gap:32px; }
.flex1 { flex:1; } .flex58 { flex:58; } .flex42 { flex:42; }
.stack { display:flex; flex-direction:column; gap:20px; }
.card { background:#fff; border-radius:16px; padding:32px 36px; display:flex; flex-direction:column; gap:20px; }
.item { display:flex; flex-direction:column; gap:4px; }
.item-head { font-size:26px; line-height:1.35; }
.item-foot { font-size:24px; color:#2F5BD3; }
.line { font-size:26px; line-height:1.35; }
.ph { color:#2F5BD3; font-style:italic; }
table { width:100%; border-collapse:collapse; font-size:28px; background:#fff; }
table.tight { font-size:24px; }
th { background:#18214A; color:#F5F6F8; font-weight:600; text-align:right; padding:14px 18px; }
td { padding:14px 18px; text-align:right; border-bottom:1px solid #E3E6EC; }
td:first-child { text-align:left; }
tr.total td { background:#E9ECF2; }
ol { font-size:26px; line-height:1.4; margin:0; padding-left:32px; }
.draft { font-size:18px; font-weight:600; color:#8A5A00; background:#FFF3D6; border-radius:6px; padding:4px 10px; }
.footer { position:absolute; left:128px; bottom:56px; width:1664px; font-size:22px; color:#6B7385; }
.notes { display:none; position:absolute; left:0; right:0; bottom:0; background:#18214A; color:#F5F6F8;
  font-size:24px; line-height:1.4; padding:24px 128px; }
body.show-notes .notes { display:block; }
#hint { position:fixed; right:16px; bottom:12px; color:#8A8F9C; font:13px system-ui, sans-serif; }
#hint a { color:#8A8F9C; }
@media print {
  @page { size:1920px 1080px; margin:0; }
  html,body { background:#fff; overflow:visible; height:auto; }
  #stage { position:static; transform:none !important; }
  .slide { display:flex !important; position:relative; width:1920px; height:1080px; page-break-after:always; break-after:page; }
  .notes, #hint { display:none !important; }
}
"""

JS = """
(function(){
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var stage = document.getElementById('stage');
  var i = Math.max(0, slides.findIndex(function(s){ return '#' + s.id === location.hash; }));
  function show(n){ i = Math.min(slides.length - 1, Math.max(0, n));
    slides.forEach(function(s, k){ s.classList.toggle('active', k === i); });
    history.replaceState(null, '', '#' + slides[i].id); }
  function fit(){ var s = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = 'translate(-50%,-50%) scale(' + s + ')'; stage.style.transformOrigin = 'center center'; }
  document.addEventListener('keydown', function(e){
    if (['ArrowRight','PageDown',' '].indexOf(e.key) > -1) { e.preventDefault(); show(i + 1); }
    if (['ArrowLeft','PageUp'].indexOf(e.key) > -1) { e.preventDefault(); show(i - 1); }
    if (e.key === 'Home') show(0);
    if (e.key === 'End') show(slides.length - 1);
    if (e.key === 'n' || e.key === 'N') document.body.classList.toggle('show-notes');
  });
  document.addEventListener('click', function(e){ if (e.target.closest('a')) return;
    show(e.clientX > innerWidth / 3 ? i + 1 : i - 1); });
  addEventListener('resize', fit); fit(); show(i);
})();
"""


def build(data_path):
    d, prev = load_weeks(data_path)
    inputs = json.loads(INPUTS_PATH.read_text())
    week_key = data_path.stem.removeprefix("week-")
    week = inputs.get("weeks", {}).get(week_key, {})

    ctx = {
        "rows": property_rows(d, inputs),
        "social_win": span_label(d["week_label"]),
        "gbp_win": span_label(d.get("gbp_window_label", d["week_label"])),
    }
    footer = f"Carbon Residential · Organic Brief · {d['week_label']}"
    builders = [
        ("scoreboard", lambda: build_scoreboard(d, prev, inputs, ctx)),
        ("winslosses", lambda: build_winslosses(d, prev, inputs, ctx, week)),
        ("reviews", lambda: build_reviews(d, inputs, ctx, week)),
        ("priority", lambda: build_priority(d, inputs, ctx, week)),
        ("actions", lambda: build_actions(inputs, ctx, week)),
    ]
    slides = []
    for n, (sid, fn) in enumerate(builders, 1):
        inner, notes = fn()
        slides.append(slide(sid, inner, notes, f"{footer} · {n}"))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Organic Brief · {esc(d['week_label'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div id="stage">
{chr(10).join(slides)}
</div>
<p id="hint">← → to move · N for notes · <a href="index.html">Detail Pack</a></p>
<script>{JS}</script>
</body>
</html>
"""


def main():
    if len(sys.argv) != 2:
        print("usage: build_brief.py data/week-YYYY-MM-DD.json", file=sys.stderr)
        sys.exit(1)
    OUT_PATH.write_text(build(Path(sys.argv[1])))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
