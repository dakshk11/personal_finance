from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self.attempts: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = datetime.now(UTC)
        bucket = self.attempts[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


auth_rate_limiter = InMemoryRateLimiter(limit=12, window_seconds=60)

