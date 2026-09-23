from __future__ import annotations

import random
import time


class BlockedError(Exception):
    """Raised when a source appears to be rate-limiting/blocking us (empty
    body where content was expected, a 403, a CloudFront/WAF error page).
    The runner stops the whole batch immediately when this is raised rather
    than continuing to hammer the source."""


def polite_delay(min_seconds: float = 5.0, max_seconds: float = 12.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))
