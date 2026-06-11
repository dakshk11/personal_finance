from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta


class AlpacaAccountRateLimiter:
    def __init__(self, limit: int = 200, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self.calls: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, key_fingerprint: str, calls: int = 1) -> bool:
        now = datetime.now(UTC)
        bucket = self.calls[key_fingerprint]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) + calls > self.limit:
            return False
        for _ in range(calls):
            bucket.append(now)
        return True

    def remaining(self, key_fingerprint: str) -> int:
        now = datetime.now(UTC)
        bucket = self.calls[key_fingerprint]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        return max(0, self.limit - len(bucket))


alpaca_account_rate_limiter = AlpacaAccountRateLimiter(limit=200, window_seconds=60)
