"""Regression tests for scripts/gbp_window.py.

These exist because of one recurring bug: GBP posts publish Friday at 12:00
local, which is both day 1 of the window and the day 100% of GBP posts land
on, so any off-by-one at the window boundary silently misplaces an entire
week's post count. Every test below targets that boundary directly.

Run with: python3 scripts/test_gbp_window.py
"""

from datetime import date

from gbp_window import (
    assert_matching_windows,
    count_gbp_posts_by_property,
    count_gbp_posts_in_window,
    is_published_gbp_post,
    local_date_of,
    resolve_gbp_windows,
    to_query_range,
)

FAILURES = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        FAILURES.append(name)


def gmb_post(date_time: str, timezone: str, status: str = "PUBLISHED") -> dict:
    return {
        "publicationDate": {"dateTime": date_time, "timezone": timezone},
        "providers": [{"network": "gmb", "status": status}],
    }


def main():
    windows = resolve_gbp_windows(date(2026, 9, 4))
    current_start, current_end = windows["current_start"], windows["current_end"]
    prior_start, prior_end = windows["prior_start"], windows["prior_end"]

    check("current window is Sep 4 - Sep 10", (current_start, current_end) == (date(2026, 9, 4), date(2026, 9, 10)))
    check("prior window is Aug 28 - Sep 3", (prior_start, prior_end) == (date(2026, 8, 28), date(2026, 9, 3)))

    # (a) A post at Friday 12:00:00 local on the FIRST day of the window
    # counts in the current window and does NOT appear in the prior window.
    post_a = gmb_post("2026-09-04T12:00:00", "America/Chicago")
    check(
        "(a) Friday noon on window's first day -> current window only",
        count_gbp_posts_in_window([post_a], current_start, current_end) == 1
        and count_gbp_posts_in_window([post_a], prior_start, prior_end) == 0,
    )

    # (b) A post at Thursday 23:59:59 local on the LAST day of the window
    # counts in the current window.
    post_b = gmb_post("2026-09-10T23:59:59", "America/Chicago")
    check(
        "(b) Thursday 23:59:59 on window's last day -> counts in current window",
        count_gbp_posts_in_window([post_b], current_start, current_end) == 1,
    )

    # (c) A post at Friday 00:00:00 local on the day AFTER the window ends
    # counts in neither window.
    post_c = gmb_post("2026-09-11T00:00:00", "America/Chicago")
    check(
        "(c) Friday 00:00:00 the day after the window ends -> counts in neither window",
        count_gbp_posts_in_window([post_c], current_start, current_end) == 0
        and count_gbp_posts_in_window([post_c], prior_start, prior_end) == 0,
    )

    # (d) The same Friday-noon post is bucketed identically for a brand in
    # America/New_York, America/Chicago and America/Mexico_City.
    tz_posts = [
        gmb_post("2026-09-04T12:00:00", "America/New_York"),
        gmb_post("2026-09-04T12:00:00", "America/Chicago"),
        gmb_post("2026-09-04T12:00:00", "America/Mexico_City"),
    ]
    check(
        "(d) Friday-noon post buckets identically across NY/Chicago/Mexico_City",
        all(count_gbp_posts_in_window([p], current_start, current_end) == 1 for p in tz_posts),
    )

    # (e) A gmb provider with status PENDING inside the window is not counted.
    post_e = gmb_post("2026-09-05T09:00:00", "America/Chicago", status="PENDING")
    check(
        "(e) PENDING gmb post inside the window is not counted",
        count_gbp_posts_in_window([post_e], current_start, current_end) == 0,
    )
    check("(e) is_published_gbp_post rejects PENDING", not is_published_gbp_post(post_e))

    # A post with multiple providers counts once, and only if the gmb
    # provider itself is PUBLISHED (part of required-fix item 4).
    multi_provider_published = {
        "publicationDate": {"dateTime": "2026-09-05T09:00:00", "timezone": "America/Chicago"},
        "providers": [
            {"network": "facebook", "status": "PUBLISHED"},
            {"network": "gmb", "status": "PUBLISHED"},
        ],
    }
    multi_provider_pending_gmb = {
        "publicationDate": {"dateTime": "2026-09-05T09:00:00", "timezone": "America/Chicago"},
        "providers": [
            {"network": "facebook", "status": "PUBLISHED"},
            {"network": "gmb", "status": "PENDING"},
        ],
    }
    check(
        "multi-provider post counts once when gmb is PUBLISHED",
        count_gbp_posts_in_window([multi_provider_published], current_start, current_end) == 1,
    )
    check(
        "multi-provider post does not count when gmb is PENDING (even if facebook is PUBLISHED)",
        count_gbp_posts_in_window([multi_provider_pending_gmb], current_start, current_end) == 0,
    )

    # (f) Sum of per-property Posts Published equals the headline Posts
    # Published.
    posts_by_property = {
        "Lakeside/Lakeview": [gmb_post("2026-09-04T12:00:00", "America/Chicago")],
        "The Benton": [gmb_post("2026-09-04T12:00:00", "America/Chicago")],
        "Santa Fe": [gmb_post("2026-09-11T00:00:00", "America/Chicago")],  # outside window
    }
    per_property = count_gbp_posts_by_property(posts_by_property, current_start, current_end)
    headline = sum(per_property.values())
    check(
        "(f) sum of per-property posts_published equals headline total",
        headline == 2 and per_property["Santa Fe"] == 0,
    )

    # local_date_of must not perform any timezone conversion.
    check(
        "local_date_of reads the calendar date verbatim, no UTC conversion",
        local_date_of({"dateTime": "2026-09-04T23:30:00", "timezone": "America/Chicago"}) == date(2026, 9, 4),
    )

    # to_query_range produces inclusive local instants.
    check(
        "to_query_range covers 00:00:00 through 23:59:59 inclusive",
        to_query_range(current_start, current_end) == ("2026-09-04T00:00:00", "2026-09-10T23:59:59"),
    )

    # assert_matching_windows: matching windows pass silently, divergent ones raise.
    assert_matching_windows((current_start, current_end), (current_start, current_end), label="test-match")
    check("assert_matching_windows accepts identical windows", True)

    raised = False
    try:
        assert_matching_windows((current_start, current_end), (prior_start, prior_end), label="test-mismatch")
    except AssertionError:
        raised = True
    check("assert_matching_windows raises loudly on divergent windows", raised)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        raise SystemExit(1)
    print("All gbp_window regression tests passed.")


if __name__ == "__main__":
    main()
