"""Builds monthly.html from a data/monthly-*.json file.

Separate from build_report.py / AUTOMATION.md on purpose: this report is
built by hand whenever Val asks for a refresh, not by the Friday weekly
automation. It reuses the weekly report's visual system (same CSS, same
color palette, same card components) via scripts/template_monthly.html,
but shows calendar-month totals with no comparison -- same approach as
the Quarterly Report (build_quarterly_report.py), just a narrower window.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_report import (  # noqa: E402
    CHANNEL_COLORS, esc, fmt, mini_bar, channel_bar_row, post_channel_chips,
    gbp_metric_row, gbp_property_card, property_views_stacked_chart,
    url_tracking_card, gmb_url_tracking_card,
)
from build_quarterly_report import (  # noqa: E402
    total_tile, property_card_total,
)


def build(data_path: Path) -> str:
    data = json.loads(data_path.read_text())

    kpis = data["kpis"]
    kpi_html = "".join([
        total_tile("Followers", kpis["followers"]),
        total_tile("Posts", kpis["posts"]),
        total_tile("Engagement", kpis["engagement"]),
        total_tile("Views", kpis["views"]),
    ])

    fbc = data["followers_by_channel"]
    fbc_max = max(c["current"] for c in fbc)
    followers_chart = "".join(
        channel_bar_row(c["channel"], c["current"], fbc_max) for c in fbc
    )

    pbc = data["posts_by_channel"]
    pbc_max = max(c["current"] for c in pbc)
    posts_chart = "".join(
        channel_bar_row(c["channel"], c["current"], pbc_max) for c in pbc
    )

    vbc = data["views_by_channel"]
    vbc_max = max(c["current"] for c in vbc)
    views_by_channel_chart = "".join(
        channel_bar_row(c["channel"], c["current"], vbc_max) for c in vbc
    )

    props = sorted(data["properties"], key=lambda p: p["views"]["current"], reverse=True)
    views_max = max(p["views"]["current"] for p in props)
    views_chart = property_views_stacked_chart(props, aria_note=f" {data['month_label']}.")

    maxes = {
        "followers": max(p["followers"]["current"] for p in props),
        "posts": max(p["posts"]["current"] for p in props),
        "engagement": max(p["engagement"]["current"] for p in props),
        "views": views_max,
    }
    property_cards = "".join(property_card_total(p, maxes) for p in props)

    gmb = data["google_business"]
    gmb_html = "".join([
        total_tile("Posts published", gmb["posts_published"]),
        total_tile("Reach · search", gmb["reach_search"]),
        total_tile("Reach · maps", gmb["reach_maps"]),
        total_tile("Website clicks", gmb["website_clicks"]),
        total_tile("Phone clicks", gmb["phone_clicks"]),
        total_tile("Directions clicks", gmb["directions_clicks"]),
    ])

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
            total_tile("Views", gmb_url_tracking["views"]),
            total_tile("Sessions", gmb_url_tracking["sessions"]),
            total_tile("Engaged sessions", gmb_url_tracking["engaged_sessions"]),
            total_tile("Key events", gmb_url_tracking["key_events"]),
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
    <p class="section-sub">Traffic that lands on each property's site from its Google Business Profile (Google Analytics, source: GMB / GMB), summed across the month.</p>
    <div class="stat-grid">{gmb_ut_html}</div>
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
            total_tile("Views", url_tracking["views"]),
            total_tile("Sessions", url_tracking["sessions"]),
            total_tile("Engaged sessions", url_tracking["engaged_sessions"]),
            total_tile("Tours", url_tracking["tours"]),
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
    <p class="section-sub">Traffic from Facebook Group posts landing on each property's site (Google Analytics), summed across the month.</p>
    <div class="stat-grid">{url_tracking_html}</div>
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

    template = (REPO_ROOT / "scripts" / "template_monthly.html").read_text()
    out = template
    out = out.replace("{{MONTH_LABEL}}", esc(data["month_label"]))
    out = out.replace("{{KPI_TILES}}", kpi_html)
    out = out.replace("{{FOLLOWERS_CHART}}", followers_chart)
    out = out.replace("{{POSTS_CHART}}", posts_chart)
    out = out.replace("{{VIEWS_BY_CHANNEL_CHART}}", views_by_channel_chart)
    out = out.replace("{{VIEWS_CHART}}", views_chart)
    out = out.replace("{{PROPERTY_CARDS}}", property_cards)
    out = out.replace("{{GMB_TILES}}", gmb_html)
    out = out.replace("{{GBP_PROPERTY_CARDS}}", gbp_property_cards)
    out = out.replace("{{GMB_URL_TRACKING_SECTION}}", gmb_url_tracking_section)
    out = out.replace("{{URL_TRACKING_SECTION}}", url_tracking_section)
    out = out.replace("{{GENERATED_NOTE}}", esc(data["generated_note"]))
    out = out.replace("{{CHANNEL_CSS_VARS_DARK}}", channel_css_vars)
    out = out.replace("{{CHANNEL_CSS_VARS_LIGHT}}", channel_css_vars_light)
    return out


def main():
    if len(sys.argv) != 2:
        print("usage: build_monthly_report.py data/monthly-<label>.json")
        sys.exit(1)
    data_path = Path(sys.argv[1])
    html = build(data_path)
    out_path = REPO_ROOT / "monthly.html"
    out_path.write_text(html)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
