import asyncio
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.alpaca_recommendation_quotes import (
    ALPACA_MAX_EQUITY_SYMBOLS,
    ALPACA_MAX_OPTION_QUOTES,
    _ALPACA_SSL_CONTEXT,
    create_quote_session,
    _wait_for_alpaca_auth,
    build_quote_snapshot,
    map_alpaca_option_quote,
    map_alpaca_stock_quote,
    normalize_equity_symbols,
    pop_quote_session,
    stream_alpaca_session,
)


class AlpacaRecommendationQuotesTests(unittest.TestCase):
    def test_symbols_normalize_dedupe_and_cap_at_30(self) -> None:
        raw = ["aapl", "MSFT", "AAPL", "bad symbol"] + [f"T{i}" for i in range(35)]

        accepted, rejected = normalize_equity_symbols(raw)

        self.assertEqual(accepted[:2], ["AAPL", "MSFT"])
        self.assertEqual(len(accepted), ALPACA_MAX_EQUITY_SYMBOLS)
        self.assertIn("BAD SYMBOL", rejected)
        self.assertGreater(len(rejected), 1)

    def test_option_quote_subscription_cap_constant(self) -> None:
        self.assertEqual(ALPACA_MAX_OPTION_QUOTES, 200)

    def test_maps_alpaca_stock_quote_frame(self) -> None:
        mapped = map_alpaca_stock_quote({"T": "q", "S": "AAPL", "bp": 190.1, "ap": 190.2, "bs": 3, "as": 5, "t": "2026-06-07T16:00:00Z"})

        self.assertEqual(mapped["type"], "stock_quote")
        self.assertEqual(mapped["symbol"], "AAPL")
        self.assertEqual(mapped["bid"], 190.1)
        self.assertEqual(mapped["ask_size"], 5)

    def test_maps_alpaca_option_quote_frame(self) -> None:
        mapped = map_alpaca_option_quote({"T": "q", "S": "AAPL260619P00180000", "bp": 2.1, "ap": 2.25, "bs": 12, "as": 14})

        self.assertEqual(mapped["type"], "option_quote")
        self.assertEqual(mapped["occ_symbol"], "AAPL260619P00180000")
        self.assertEqual(mapped["bid_size"], 12)

    def test_equities_only_snapshot_skips_option_contracts(self) -> None:
        quote = SimpleNamespace(symbol="AAPL", price=190.0, close=188.0, source="Yahoo")
        with patch("app.services.alpaca_recommendation_quotes.fetch_yahoo_quote_snapshots", return_value=[quote]), patch(
            "app.services.alpaca_recommendation_quotes._fetch_option_chains"
        ) as chains:
            snapshot = asyncio.run(build_quote_snapshot(["AAPL"], include_options=False))

        chains.assert_not_called()
        self.assertEqual(snapshot["symbols"], ["AAPL"])
        self.assertEqual(snapshot["option_contracts"], [])
        self.assertEqual(snapshot["option_chains"], {"AAPL": {"puts": [], "calls": []}})

    def test_session_can_include_option_snapshot_without_streaming_options(self) -> None:
        snapshot = {
            "symbols": ["AAPL"],
            "rejected_symbols": [],
            "max_symbols": 30,
            "max_option_quotes": 200,
            "option_contracts": ["AAPL260619P00180000"],
            "quotes": [{"symbol": "AAPL"}],
            "option_chains": {"AAPL": {"puts": [], "calls": []}},
        }
        with patch("app.services.alpaca_recommendation_quotes.build_quote_snapshot", return_value=snapshot):
            created = asyncio.run(create_quote_session(user_id=1, api_key="key", api_secret="secret", symbols=["AAPL"], include_options=True, stream_options=False))

        self.assertEqual(created["option_contracts"], ["AAPL260619P00180000"])
        session = pop_quote_session(created["session_id"])
        self.assertIsNotNone(session)
        self.assertEqual(session.option_contracts, [])

    def test_snapshot_reuses_wheel_cboe_daily_cache(self) -> None:
        quote = SimpleNamespace(symbol="AAPL", price=190.0, close=188.0, source="Yahoo")
        today = date.today()
        rows = [
            _option_row("AAPL260710P00180000", "P", today + timedelta(days=32), 180.0, -0.31, 2.2, 2.4, 45.0),
            _option_row("AAPL260710C00200000", "C", today + timedelta(days=32), 200.0, 0.29, 2.0, 2.2, 43.0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cboe_daily_cache.json"
            cache_path.write_text(json.dumps({"date": today.isoformat(), "chains": {"AAPL": rows}}))
            with patch("app.services.alpaca_recommendation_quotes.fetch_yahoo_quote_snapshots", return_value=[quote]), patch(
                "app.services.alpaca_recommendation_quotes._WHEEL_CBOE_CACHE_PATH", cache_path
            ):
                snapshot = asyncio.run(build_quote_snapshot(["AAPL"], include_options=True))

        self.assertEqual(snapshot["option_contracts"], ["AAPL260710P00180000", "AAPL260710C00200000"])
        self.assertEqual(len(snapshot["option_chains"]["AAPL"]["puts"]), 1)
        self.assertEqual(len(snapshot["option_chains"]["AAPL"]["calls"]), 1)
        self.assertIsNotNone(snapshot["quotes"][0]["csp_30d"])
        self.assertIsNotNone(snapshot["quotes"][0]["cc_30d"])


class AlpacaRecommendationQuoteStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_authenticated_before_subscribing(self) -> None:
        ws = FakeWebSocket([
            '[{"T":"success","msg":"connected"}]',
            '[{"T":"success","msg":"authenticated"}]',
        ])
        sender = FakeSender()

        authenticated = await _wait_for_alpaca_auth(ws, "stock", sender.send)

        self.assertTrue(authenticated)
        self.assertEqual(sender.messages, [])

    async def test_auth_error_is_forwarded_to_client(self) -> None:
        ws = FakeWebSocket(['[{"T":"error","code":401,"msg":"auth failed"}]'])
        sender = FakeSender()

        authenticated = await _wait_for_alpaca_auth(ws, "stock", sender.send)

        self.assertFalse(authenticated)
        self.assertEqual(sender.messages[0]["status"], "error")
        self.assertEqual(sender.messages[0]["message"], "Alpaca rejected the saved API key or secret.")

    async def test_stream_uses_certifi_ssl_context(self) -> None:
        session = type(
            "Session",
            (),
            {
                "snapshot": {"symbols": ["AAPL"], "option_contracts": [], "quotes": [], "option_chains": {}},
                "symbols": ["AAPL"],
                "option_contracts": [],
                "api_key": "key",
                "api_secret": "secret",
            },
        )()
        sender = FakeSender()

        with patch("app.services.alpaca_recommendation_quotes.websockets.connect", return_value=FakeConnectWebSocket()) as connect:
            await stream_alpaca_session(session, sender.send)

        self.assertIs(connect.call_args.kwargs["ssl"], _ALPACA_SSL_CONTEXT)


class FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)

    async def recv(self) -> str:
        return self.messages.pop(0)


class FakeConnectWebSocket:
    async def __aenter__(self) -> "FakeConnectWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send(self, message: str) -> None:
        return None

    async def recv(self) -> str:
        return '[{"T":"success","msg":"authenticated"}]'

    def __aiter__(self) -> "FakeConnectWebSocket":
        return self

    async def __anext__(self) -> str:
        raise StopAsyncIteration


class FakeSender:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, message: dict) -> None:
        self.messages.append(message)


def _option_row(occ_symbol: str, option_type: str, expiry: date, strike: float, delta: float, bid: float, ask: float, iv: float) -> dict:
    mid = round((bid + ask) / 2, 2)
    dte = (expiry - date.today()).days
    return {
        "symbol": "AAPL",
        "occ_symbol": occ_symbol,
        "option_type": option_type,
        "expiry": expiry.isoformat(),
        "dte": dte,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "iv": iv,
        "delta": delta,
        "open_interest": 100,
        "volume": 10,
        "annualized_yield": round((mid / strike) * 100 * (365 / dte), 2),
        "pct_away": None,
        "pop": round((1 - abs(delta)) * 100, 1),
        "stock_price": 190.0,
        "capital_required": round(strike * 100, 2) if option_type == "P" else None,
    }


if __name__ == "__main__":
    unittest.main()
