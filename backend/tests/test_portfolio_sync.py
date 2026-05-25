from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import PortfolioSyncCredential, PortfolioSyncProviderCredential, PortfolioSyncSnapshot, User
from app.schemas.common import PortfolioAnalyzerHoldingOut, PortfolioAnalyzerOut
from app.services import portfolio_sync


class PortfolioSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self) -> tuple[object, User]:
        db = self.Session()
        user = User(email="sync@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_missing_snaptrade_env_returns_setup_required_and_no_redirect(self) -> None:
        db, user = self._seed_user()
        with patch("app.services.portfolio_sync.get_settings", return_value=_settings(configured=False)):
            status = portfolio_sync.get_status(db, user.id)

            self.assertFalse(status.configured)
            self.assertFalse(status.connected)
            self.assertIn("SnapTrade is not configured", status.warnings[0])
            with self.assertRaises(portfolio_sync.PortfolioSyncConfigurationError):
                portfolio_sync.create_connection_redirect(db, user.id, client=MockSnapTrade())

    def test_register_connect_stores_encrypted_user_secret_and_returns_redirect(self) -> None:
        db, user = self._seed_user()
        client = MockSnapTrade()
        with patch("app.services.portfolio_sync.get_settings", return_value=_settings()):
            result = portfolio_sync.create_connection_redirect(db, user.id, client=client)

        credential = db.scalar(select(PortfolioSyncCredential).where(PortfolioSyncCredential.user_id == user.id))
        self.assertIsNotNone(credential)
        assert credential is not None
        self.assertEqual(credential.provider_user_id, f"directindex-user-{user.id}")
        self.assertNotIn("secret-123", credential.encrypted_user_secret)
        self.assertTrue(credential.user_secret_fingerprint.startswith("sha256:"))
        self.assertEqual(result.redirect_url, "https://snaptrade.test/connect")
        self.assertEqual(client.authentication.register_count, 1)
        self.assertEqual(client.authentication.login_count, 1)

    def test_store_provider_credentials_encrypts_consumer_key_and_configures_provider(self) -> None:
        db, user = self._seed_user()
        with patch("app.services.portfolio_sync.get_settings", return_value=_settings(configured=False)):
            status = portfolio_sync.save_provider_credentials(
                db,
                user.id,
                client_id=" browser-client-id ",
                consumer_key="browser-consumer-key",
            )

            stored = db.scalar(select(PortfolioSyncProviderCredential).where(PortfolioSyncProviderCredential.user_id == user.id))

            self.assertTrue(status.configured)
            self.assertEqual(status.source, "database")
            self.assertEqual(status.client_id, "browser-client-id")
            self.assertTrue(status.consumer_key_fingerprint.startswith("sha256:"))
            self.assertTrue(portfolio_sync.provider_configured(db, user.id))
            self.assertFalse(portfolio_sync.provider_configured())

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertNotIn("browser-consumer-key", stored.encrypted_consumer_key)
        self.assertEqual(stored.client_id, "browser-client-id")

    def test_stored_provider_credentials_allow_connect_without_env(self) -> None:
        db, user = self._seed_user()
        client = MockSnapTrade()
        with patch("app.services.portfolio_sync.get_settings", return_value=_settings(configured=False)):
            portfolio_sync.save_provider_credentials(db, user.id, client_id="browser-client-id", consumer_key="browser-consumer-key")
            result = portfolio_sync.create_connection_redirect(db, user.id, client=client)

        self.assertEqual(result.redirect_url, "https://snaptrade.test/connect")
        self.assertEqual(client.authentication.register_count, 1)
        self.assertEqual(client.authentication.login_count, 1)

    def test_delete_stored_provider_credentials_clears_user_secret_and_snapshot(self) -> None:
        db, user = self._seed_user()
        client = MockSnapTrade()
        with patch("app.services.portfolio_sync.get_settings", return_value=_settings(configured=False)):
            portfolio_sync.save_provider_credentials(db, user.id, client_id="browser-client-id", consumer_key="browser-consumer-key")
            portfolio_sync.create_connection_redirect(db, user.id, client=client)
            db.add(
                PortfolioSyncSnapshot(
                    user_id=user.id,
                    provider="snaptrade",
                    accounts_json="[]",
                    holdings_json="[]",
                    warnings_json="[]",
                )
            )
            db.commit()

            status = portfolio_sync.delete_provider_credentials(db, user.id)

            self.assertFalse(status.configured)
            self.assertEqual(status.source, "none")
            self.assertFalse(portfolio_sync.provider_configured(db, user.id))

        self.assertIsNone(db.scalar(select(PortfolioSyncProviderCredential).where(PortfolioSyncProviderCredential.user_id == user.id)))
        self.assertIsNone(db.scalar(select(PortfolioSyncCredential).where(PortfolioSyncCredential.user_id == user.id)))
        self.assertIsNone(db.scalar(select(PortfolioSyncSnapshot).where(PortfolioSyncSnapshot.user_id == user.id)))

    def test_sync_maps_multiple_accounts_and_missing_cost_basis_warning(self) -> None:
        db, user = self._seed_user()
        client = MockSnapTrade()
        with (
            patch("app.services.portfolio_sync.get_settings", return_value=_settings()),
            patch("app.services.portfolio_sync.analyze_portfolio_holdings", side_effect=_mock_analysis),
        ):
            portfolio_sync.create_connection_redirect(db, user.id, client=client)
            summary = portfolio_sync.sync_portfolio(db, user.id, client=client)

        self.assertEqual(summary.account_count, 2)
        self.assertEqual(summary.holding_count, 2)
        self.assertEqual({holding.symbol for holding in summary.holdings}, {"AAPL", "MSFT"})
        self.assertEqual({holding.brokerage_name for holding in summary.holdings}, {"Fidelity", "Schwab"})
        self.assertEqual(client.account_information.requested_account_ids, ["taxable-1", "ira-1"])
        self.assertEqual(client.account_information.list_accounts_count, 0)
        self.assertEqual(client.account_information.deprecated_all_holdings_count, 0)
        self.assertEqual(client.account_information.deprecated_account_holdings_count, 0)
        self.assertTrue(any("Cost basis missing" in warning for warning in summary.warnings))
        self.assertTrue(any("AAPL is" in warning for warning in summary.concentration_warnings))
        self.assertTrue(any("Information Technology is" in warning for warning in summary.concentration_warnings))

    def test_summary_reuses_persisted_snapshot_without_provider_calls(self) -> None:
        db, user = self._seed_user()
        client = MockSnapTrade()
        with (
            patch("app.services.portfolio_sync.get_settings", return_value=_settings()),
            patch("app.services.portfolio_sync.analyze_portfolio_holdings", side_effect=_mock_analysis),
        ):
            portfolio_sync.create_connection_redirect(db, user.id, client=client)
            portfolio_sync.sync_portfolio(db, user.id, client=client)
            calls_after_sync = client.account_information.positions_count
            summary = portfolio_sync.get_summary(db, user.id)

        self.assertEqual(client.account_information.positions_count, calls_after_sync)
        self.assertGreater(summary.total_market_value, 0)
        self.assertEqual(summary.status.holding_count, 2)


class MockSnapTrade:
    def __init__(self) -> None:
        self.authentication = MockAuthentication()
        self.connections = MockConnections()
        self.account_information = MockAccountInformation()


class MockAuthentication:
    def __init__(self) -> None:
        self.register_count = 0
        self.login_count = 0

    def register_snap_trade_user(self, user_id: str) -> dict[str, str]:
        self.register_count += 1
        return {"userSecret": "secret-123", "userId": user_id}

    def login_snap_trade_user(self, user_id: str, user_secret: str, custom_redirect: str) -> dict[str, str]:
        self.login_count += 1
        self.last_login = {"user_id": user_id, "user_secret": user_secret, "custom_redirect": custom_redirect}
        return {"redirectURI": "https://snaptrade.test/connect"}


class MockConnections:
    def list_brokerage_authorizations(self, user_id: str, user_secret: str) -> list[dict[str, object]]:
        del user_id, user_secret
        return [
            {"id": "auth-1", "brokerage": {"name": "Fidelity"}},
            {"id": "auth-2", "brokerage": {"name": "Schwab"}},
        ]

    def list_brokerage_authorization_accounts(self, authorization_id: str, user_id: str, user_secret: str) -> list[dict[str, object]]:
        del user_id, user_secret
        if authorization_id == "auth-1":
            return [{"id": "taxable-1", "name": "Taxable", "institution_name": "Fidelity", "type": "taxable"}]
        return [{"id": "ira-1", "name": "Rollover IRA", "institution_name": "Schwab", "type": "ira"}]


class MockAccountInformation:
    def __init__(self) -> None:
        self.list_accounts_count = 0
        self.positions_count = 0
        self.deprecated_all_holdings_count = 0
        self.deprecated_account_holdings_count = 0
        self.requested_account_ids: list[str] = []

    def list_user_accounts(self, user_id: str, user_secret: str) -> list[dict[str, object]]:
        del user_id, user_secret
        self.list_accounts_count += 1
        return [
            {"id": "taxable-1", "name": "Taxable", "institution_name": "Fidelity", "type": "taxable"},
            {"id": "ira-1", "name": "Rollover IRA", "institution_name": "Schwab", "type": "ira"},
        ]

    def get_all_user_holdings(self, user_id: str, user_secret: str) -> list[dict[str, object]]:
        del user_id, user_secret
        self.deprecated_all_holdings_count += 1
        raise AssertionError("Deprecated SnapTrade /api/v1/holdings endpoint should not be called.")

    def get_user_holdings(self, account_id: str, user_id: str, user_secret: str) -> dict[str, object]:
        del account_id, user_id, user_secret
        self.deprecated_account_holdings_count += 1
        raise AssertionError("Deprecated SnapTrade /api/v1/accounts/{accountId}/holdings endpoint should not be called.")

    def get_user_account_positions(self, account_id: str, user_id: str, user_secret: str) -> dict[str, object]:
        del user_id, user_secret
        self.positions_count += 1
        self.requested_account_ids.append(account_id)
        if account_id == "taxable-1":
            return {
                "account": {"id": "taxable-1", "name": "Taxable", "institution_name": "Fidelity"},
                "positions": [
                    {
                        "symbol": {"raw_symbol": "AAPL", "id": "sym-aapl"},
                        "quantity": 100,
                        "lastPrice": 150,
                        "averagePurchasePrice": 120,
                    }
                ],
            }
        return {
            "account": {"id": "ira-1", "name": "Rollover IRA", "institution_name": "Schwab"},
            "positions": [
                {
                    "universal_symbol": {"symbol": "MSFT", "id": "sym-msft"},
                    "units": 10,
                    "marketValue": 3_000,
                }
            ],
        }


def _settings(configured: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        snaptrade_client_id="client-id" if configured else "",
        snaptrade_consumer_key="consumer-key" if configured else "",
        broker_sync_encryption_secret="broker-sync-test-secret-at-least-32-chars",
        frontend_origin="http://localhost:3000",
    )


def _mock_analysis(db: object, holdings: list[object], min_weight_percent: float = 0) -> PortfolioAnalyzerOut:
    del db
    prices = {"AAPL": 150.0, "MSFT": 300.0}
    rows: list[PortfolioAnalyzerHoldingOut] = []
    total_market_value = 0.0
    total_cost_basis = 0.0
    for holding in holdings:
        symbol = holding.symbol
        price = prices[symbol]
        market_value = holding.shares * price
        cost_basis = holding.shares * holding.cost_basis_per_share
        total_market_value += market_value
        total_cost_basis += cost_basis
        rows.append(
            PortfolioAnalyzerHoldingOut(
                symbol=symbol,
                shares=holding.shares,
                price=price,
                market_value=market_value,
                weight=0,
                cost_basis_per_share=holding.cost_basis_per_share,
                cost_basis=cost_basis,
                unrealized_gain_loss=market_value - cost_basis,
                unrealized_gain_loss_pct=((market_value - cost_basis) / cost_basis) if cost_basis > 0 else 0,
                valuation_signal="unknown",
                valuation_signal_label="Mock",
                data_source="mock price; mock valuation",
                warning=None,
            )
        )
    for row in rows:
        row.weight = row.market_value / total_market_value if total_market_value else 0
    return PortfolioAnalyzerOut(
        as_of_date=date(2026, 5, 24),
        min_weight_percent=min_weight_percent,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        unrealized_gain_loss=total_market_value - total_cost_basis,
        unrealized_gain_loss_pct=((total_market_value - total_cost_basis) / total_cost_basis) if total_cost_basis > 0 else 0,
        analyzed_holding_count=len(rows),
        hidden_holding_count=0,
        holdings=rows,
        warnings=["mock analyzer"],
    )


if __name__ == "__main__":
    unittest.main()
