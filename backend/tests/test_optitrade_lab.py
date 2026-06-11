import asyncio
import unittest
from unittest.mock import patch

from app.core.alpaca_rate_limit import alpaca_account_rate_limiter
from app.services.ai_advisor import api_key_fingerprint
from app.services.optitrade_lab import (
    DEFAULT_OPTITRADE_SYMBOLS,
    AlpacaRateLimitError,
    fetch_alpaca_daily_bars,
    _optitrade_chart,
    _normalize_universe,
)


class OptiTradeLabAlpacaTests(unittest.TestCase):
    def setUp(self) -> None:
        alpaca_account_rate_limiter.calls.clear()

    def test_alpaca_bar_fetch_counts_each_page_against_rate_limit(self) -> None:
        calls = []

        def fake_fetch(api_key, api_secret, symbols, start, end, page_token):
            calls.append(page_token)
            if page_token is None:
                return {
                    "bars": {"TQQQ": [{"t": "2026-01-02T00:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 1000}]},
                    "next_page_token": "next",
                }
            return {
                "bars": {"TQQQ": [{"t": "2026-01-03T00:00:00Z", "o": 10.5, "h": 12, "l": 10, "c": 11.5, "v": 1200}]},
                "next_page_token": None,
            }

        with patch("app.services.optitrade_lab._fetch_alpaca_bars_page", side_effect=fake_fetch):
            bars, call_count = asyncio.run(fetch_alpaca_daily_bars("alpaca-key", "alpaca-secret", ["TQQQ"]))

        self.assertEqual(calls, [None, "next"])
        self.assertEqual(call_count, 2)
        self.assertEqual(len(bars["TQQQ"]), 2)
        self.assertEqual(alpaca_account_rate_limiter.remaining(api_key_fingerprint("alpaca-key")), 198)

    def test_alpaca_bar_fetch_stops_when_account_rate_limit_is_exhausted(self) -> None:
        fingerprint = api_key_fingerprint("alpaca-key")
        self.assertTrue(alpaca_account_rate_limiter.allow(fingerprint, calls=200))

        with self.assertRaises(AlpacaRateLimitError):
            asyncio.run(fetch_alpaca_daily_bars("alpaca-key", "alpaca-secret", ["TQQQ"]))

    def test_default_universe_includes_leveraged_etfs_and_sp500_top_20(self) -> None:
        universe = _normalize_universe(DEFAULT_OPTITRADE_SYMBOLS)

        self.assertEqual(len(universe), 23)
        self.assertEqual(universe[:3], ["TQQQ", "SOXL", "UPRO"])
        self.assertIn("NVDA", universe)
        self.assertIn("CSCO", universe)

    def test_chart_payload_includes_ohlcv_for_candlesticks(self) -> None:
        bars = [
            {"date": f"2026-01-{day:02d}", "open": 10 + day, "high": 11 + day, "low": 9 + day, "close": 10.5 + day, "volume": 1000 + day}
            for day in range(1, 60)
        ]
        chart = _optitrade_chart(
            bars,
            {"signal": "BUY"},
            {"entry": 20.0, "stop_loss": 18.0, "take_profits": [22.0, 24.0, 26.0, 28.0]},
        )

        latest = chart[-1]
        for key in ("open", "high", "low", "close", "volume"):
            self.assertIn(key, latest)
        self.assertEqual(latest["marker"], "BUY")


if __name__ == "__main__":
    unittest.main()
