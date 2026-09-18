"""Single source of truth for the Google Business Profile (GBP) reporting window.

Why this module exists
-----------------------
GBP posts publish Friday at 12:00 local time. Our GBP window is Friday-through-
Thursday, so the Friday start date is BOTH day 1 of the window AND the day that
100% of GBP posts land on. Any off-by-one at that boundary doesn't just lose a
few posts at the margin -- it silently reassigns an entire week's post count to
the adjacent week, every single time, with no partial failures to notice.

The fix is architectural, not numerical: GBP_CURRENT and GBP_PRIOR are resolved
ONCE, here, as calendar `date` objects. Both the scheduled-posts count and the
analytics-metrics pull must build their query ranges from the exact same
(current_start, current_end, prior_start, prior_end) tuple returned by
`resolve_gbp_windows`. There is no second derivation anywhere else in the
codebase -- if one is ever added, `assert_matching_windows` is how it gets
caught before the report ships.

Window semantics
-----------------
- Friday-through-Thursday, both ends INCLUSIVE. A window labeled "Sep 4-10"
  covers Sep 4 00:00:00.000 through Sep 10 23:59:59.999 local time. The start
  Friday belongs to the current window and never to the prior one.
- All comparisons happen in each brand's own local calendar date, taken
  directly from Metricool's `publicationDate.dateTime` (which is already
  wall-clock-local, paired with a `timezone` field) -- never converted to UTC
  or to the report server's timezone.
- A post counts for GBP only when one of its `providers` entries has
  `network == "gmb"` and `status == "PUBLISHED"`. PENDING posts, and posts on
  non-gmb networks, never count.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Mapping, Sequence


def week_bounds(current_start: date) -> tuple[date, date]:
    """Return (start, end) for the 7-day Friday-through-Thursday window
    beginning on `current_start`, both ends inclusive."""
    return current_start, current_start + timedelta(days=6)


def prior_week_bounds(current_start: date) -> tuple[date, date]:
    """Return (start, end) for the window immediately preceding
    `current_start`'s window, both ends inclusive."""
    prior_start = current_start - timedelta(days=7)
    return week_bounds(prior_start)


def resolve_gbp_windows(current_start: date) -> dict:
    """The single function both consumers (post counting and metrics pulls)
    must call. `current_start` is the Friday that opens GBP_CURRENT -- the
    only date that needs to be decided elsewhere (e.g. by the walk-back
    completeness check); everything else is derived here.

    Returns calendar `date` objects, not strings, so callers can't silently
    diverge by formatting them differently.
    """
    current_start_d, current_end_d = week_bounds(current_start)
    prior_start_d, prior_end_d = prior_week_bounds(current_start)
    return {
        "current_start": current_start_d,
        "current_end": current_end_d,
        "prior_start": prior_start_d,
        "prior_end": prior_end_d,
    }


def to_query_range(start: date, end: date) -> tuple[str, str]:
    """Convert an inclusive (start, end) calendar-date pair into the local
    wall-clock ISO instants used for Metricool's `from`/`to` query params.
    Both ends inclusive: the end instant is 23:59:59 on `end`, not midnight."""
    return f"{start.isoformat()}T00:00:00", f"{end.isoformat()}T23:59:59"


def local_date_of(publication_date: Mapping) -> date:
    """Extract the calendar date a post published on, in the brand's own
    local timezone, exactly as Metricool reports it. `publicationDate` is a
    dict like {"dateTime": "2026-08-28T10:00:00", "timezone": "America/Chicago"}.

    Metricool already returns wall-clock-local time paired with a timezone
    field, so we take the date portion of `dateTime` as-is -- no UTC
    conversion, no report-server timezone involved.
    """
    return date.fromisoformat(publication_date["dateTime"][:10])


def in_window(d: date, start: date, end: date) -> bool:
    """Inclusive-both-ends membership test."""
    return start <= d <= end


def is_published_gbp_post(post: Mapping) -> bool:
    """True iff this post has a gmb provider entry with status PUBLISHED.
    A post with multiple providers counts for GBP only if the gmb provider
    itself is PUBLISHED -- a PUBLISHED Facebook provider on the same post
    does not make it count, and a PENDING gmb provider does not either."""
    for provider in post.get("providers", []):
        if provider.get("network") == "gmb" and provider.get("status") == "PUBLISHED":
            return True
    return False


def count_gbp_posts_in_window(posts: Iterable[Mapping], start: date, end: date) -> int:
    """Count published GBP posts among `posts` whose local publication date
    falls inside [start, end] inclusive."""
    count = 0
    for post in posts:
        if not is_published_gbp_post(post):
            continue
        if in_window(local_date_of(post["publicationDate"]), start, end):
            count += 1
    return count


def count_gbp_posts_by_property(
    posts_by_property: Mapping[str, Sequence[Mapping]], start: date, end: date
) -> dict[str, int]:
    """Same as count_gbp_posts_in_window, applied per property. Returns a
    dict of property name -> count so the caller can both populate
    gbp_by_property and sum it to cross-check the headline total (see
    regression test (f))."""
    return {
        name: count_gbp_posts_in_window(posts, start, end)
        for name, posts in posts_by_property.items()
    }


def assert_matching_windows(posts_window: tuple, metrics_window: tuple, label: str = "GBP window") -> None:
    """The build-time divergence check. `posts_window` and `metrics_window`
    are each (start, end) date tuples -- one derived for the getScheduledPosts
    count, one derived for the getAnalyticsDataByMetrics pull. Prints both to
    the build log unconditionally (so the next mismatch is visible
    immediately even when this passes) and raises loudly on any divergence.
    """
    print(f"[{label}] posts window:   {posts_window[0].isoformat()} .. {posts_window[1].isoformat()}")
    print(f"[{label}] metrics window: {metrics_window[0].isoformat()} .. {metrics_window[1].isoformat()}")
    if posts_window != metrics_window:
        raise AssertionError(
            f"{label}: posts-count window {posts_window} does not match "
            f"metrics-pull window {metrics_window}. These must be derived from "
            f"the same resolve_gbp_windows() call -- see scripts/gbp_window.py."
        )
