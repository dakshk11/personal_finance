from datetime import date
import hashlib
import math


def deterministic_price(symbol: str, price_date: date) -> float:
    key = f"{symbol}:{price_date.isoformat()}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    seed = int(digest[:8], 16)
    base = 40 + (int(hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:6], 16) % 500)
    day_number = price_date.toordinal()
    trend = 1 + ((day_number - date(2024, 1, 1).toordinal()) / 3650)
    cycle = 1 + 0.08 * math.sin((seed % 365) / 365 * math.tau)
    return round(base * trend * cycle, 2)

