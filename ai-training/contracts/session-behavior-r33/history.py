"""A numeric, causal navigation view. Session lookup and eligibility belong to the caller."""

from collections import deque
from math import log1p
from statistics import median

SCHEMA = "idps-navigation-prefix-r33-v1"
ORDER = (
    "prior_distinct_fraction",
    "prior_change_fraction",
    "target_prior_fraction",
    "target_recency",
    "log_current_gap_seconds",
    "log_median_gap_seconds",
    "log_median_absolute_deviation",
    "log_gap_range_seconds",
)
WINDOW = 5


class Prefix:
    """Private bounded state for one server-validated session in one observation scope."""

    def __init__(self):
        self.previous = deque(maxlen=WINDOW)
        self.watermark = -1
        self.pending_route = None

    def observe(self, second, route):
        if type(second) is not int or second < 0 or not route:
            raise ValueError("invalid route observation")
        if second < self.watermark:
            self.previous.clear()
            self.pending_route = None
            return None, "CLOCK_REGRESSION"
        if second > self.watermark:
            if self.watermark >= 0:
                self.previous.append((self.watermark, self.pending_route))
            self.pending_route = route
            self.watermark = second
        else:
            # Simultaneous requests all see the prefix before this entire second.
            self.pending_route = None
        history = list(self.previous)
        if len(history) < WINDOW:
            return None, "SHORT_PREFIX"
        times = [t for t, _ in history] + [second]
        gaps = [b - a for a, b in zip(times, times[1:])]
        if any(r is None for _, r in history) or min(gaps) <= 0:
            return None, "CLOCK_TIE"
        if max(gaps) > 1800:
            return None, "SESSION_GAP"
        past = [r for _, r in history]
        recent = [i for i, r in enumerate(reversed(past)) if r == route]
        mid = median(gaps)
        return (
            len(set(past)) / WINDOW,
            sum(a != b for a, b in zip(past, past[1:])) / (WINDOW - 1),
            past.count(route) / WINDOW,
            (WINDOW - recent[0]) / WINDOW if recent else 0,
            log1p(gaps[-1]),
            log1p(mid),
            log1p(median(abs(g - mid) for g in gaps)),
            log1p(max(gaps) - min(gaps)),
        ), "AVAILABLE"
