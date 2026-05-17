import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import ThirteenFFiling, ThirteenFHolding, ThirteenFWatch, User
from app.services.sec_filings import (
    current_13f_filing_window,
    next_13f_check_at,
    next_13f_filing_window_start,
    parse_13f_info_table,
    search_13f_managers,
    simulate_13f_copycat_performance,
)


class SecFilingTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def test_current_13f_window_uses_45_day_deadline(self) -> None:
        window = current_13f_filing_window(date(2026, 5, 15))

        self.assertIsNotNone(window)
        self.assertEqual(window.report_period, date(2026, 3, 31))
        self.assertEqual(window.start_date, date(2026, 4, 1))
        self.assertEqual(window.due_date, date(2026, 5, 15))

    def test_next_check_repeats_every_two_hours_until_due_period_posts(self) -> None:
        now = datetime(2026, 5, 15, 12, 0)
        next_check = next_13f_check_at(now, latest_report_period=date(2025, 12, 31))

        self.assertEqual(next_check, now + timedelta(hours=2))

    def test_next_check_waits_for_next_window_after_current_report_posts(self) -> None:
        next_check = next_13f_check_at(datetime(2026, 5, 15, 12, 0), latest_report_period=date(2026, 3, 31))

        self.assertEqual(next_check, datetime(2026, 7, 1, 6, 0))

    def test_next_window_after_deadline_is_next_quarter(self) -> None:
        self.assertEqual(next_13f_filing_window_start(date(2026, 5, 16)), date(2026, 7, 1))

    def test_known_manager_search_supports_manager_name(self) -> None:
        result = search_13f_managers("Warren Buffett", fetch_remote=False)

        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].cik, "0001067983")
        self.assertIn("BERKSHIRE", result.candidates[0].manager_name)

    def test_13f_info_table_parser_resolves_common_symbols_and_weights(self) -> None:
        holdings = parse_13f_info_table(
            """
            <informationTable>
              <infoTable>
                <nameOfIssuer>APPLE INC</nameOfIssuer>
                <titleOfClass>COM</titleOfClass>
                <cusip>037833100</cusip>
                <value>75000</value>
                <shrsOrPrnAmt><sshPrnamt>100000</sshPrnamt></shrsOrPrnAmt>
              </infoTable>
              <infoTable>
                <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
                <titleOfClass>COM</titleOfClass>
                <cusip>594918104</cusip>
                <value>25000</value>
                <shrsOrPrnAmt><sshPrnamt>50000</sshPrnamt></shrsOrPrnAmt>
              </infoTable>
            </informationTable>
            """
        )

        self.assertEqual([holding.symbol for holding in holdings], ["AAPL", "MSFT"])
        self.assertAlmostEqual(sum(holding.weight for holding in holdings), 1.0)
        self.assertEqual(holdings[0].value, 75_000_000)

    def test_copycat_performance_uses_cached_filings_without_mutating_downloads(self) -> None:
        db = self.Session()
        user = User(email="13f@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        watch = ThirteenFWatch(user_id=user.id, query="Buffett", manager_name="BERKSHIRE HATHAWAY INC", cik="0001067983")
        db.add(watch)
        db.commit()
        db.refresh(watch)

        first = ThirteenFFiling(
            watch_id=watch.id,
            manager_name=watch.manager_name,
            cik=watch.cik,
            form="13F-HR",
            accession_number="a1",
            filing_date=date(2025, 2, 14),
            report_period=date(2024, 12, 31),
            holdings_count=2,
            priced_holdings_count=2,
            total_value=100_000_000,
        )
        second = ThirteenFFiling(
            watch_id=watch.id,
            manager_name=watch.manager_name,
            cik=watch.cik,
            form="13F-HR",
            accession_number="a2",
            filing_date=date(2025, 5, 15),
            report_period=date(2025, 3, 31),
            holdings_count=2,
            priced_holdings_count=2,
            total_value=100_000_000,
        )
        db.add_all([first, second])
        db.commit()
        db.refresh(first)
        db.refresh(second)
        db.add_all(
            [
                ThirteenFHolding(filing_id=first.id, symbol="AAPL", cusip="037833100", issuer_name="APPLE INC", value=70_000_000, shares=100_000, weight=0.70),
                ThirteenFHolding(filing_id=first.id, symbol="MSFT", cusip="594918104", issuer_name="MICROSOFT CORP", value=30_000_000, shares=50_000, weight=0.30),
                ThirteenFHolding(filing_id=second.id, symbol="KO", cusip="191216100", issuer_name="COCA COLA CO", value=60_000_000, shares=80_000, weight=0.60),
                ThirteenFHolding(filing_id=second.id, symbol="AXP", cusip="025816109", issuer_name="AMERICAN EXPRESS CO", value=40_000_000, shares=40_000, weight=0.40),
            ]
        )
        db.commit()

        performance = simulate_13f_copycat_performance(db, watch, years=4, starting_value=100_000, today=date(2025, 8, 15))

        self.assertEqual(performance.cached_filings, 2)
        self.assertEqual(performance.cached_holdings, 4)
        self.assertEqual(len(performance.periods), 2)
        self.assertEqual(performance.periods[0].start_date, date(2025, 2, 17))
        self.assertNotEqual(performance.ending_value, performance.starting_value)


if __name__ == "__main__":
    unittest.main()
