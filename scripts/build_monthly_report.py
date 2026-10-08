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
    gbp_metric_row, gbp_property_card,
)
from build_quarterly_report import (  # noqa: E402
    total_tile, property_bar_row_total, property_card_total,
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

    props = sorted(data["properties"], key=lambda p: p["views"]["current"], reverse=True)
    views_max = max(p["views"]["current"] for p in props)
    views_chart = "".join(
        property_bar_row_total(p["name"], p["views"]["current"], views_max, p["top_channel"])
        for p in props
    )

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
    out = out.replace("{{VIEWS_CHART}}", views_chart)
    out = out.replace("{{PROPERTY_CARDS}}", property_cards)
    out = out.replace("{{GMB_TILES}}", gmb_html)
    out = out.replace("{{GBP_PROPERTY_CARDS}}", gbp_property_cards)
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
