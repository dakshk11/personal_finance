import unittest

from app.api.backtests import compare_models
from app.schemas.common import ModelComparisonRequest
from app.services.backtest import backtest_coverage, run_backtest
from app.services.direct_index_models import EXECUTABLE_DIRECT_INDEX_MODELS


class BacktestTests(unittest.TestCase):
    def test_topt_2024_is_partial_period(self) -> None:
        _, _, label, warnings = backtest_coverage("TOPT", 2024)

        self.assertIn("partial-period", label)
        self.assertTrue(any("launched" in warning for warning in warnings))

    def test_qtop_2023_is_unavailable_pre_inception(self) -> None:
        result = run_backtest("QTOP", 2023, 100_000, [])

        self.assertEqual(result.coverage_label, "unavailable - pre-inception")
        self.assertEqual(result.trade_count, 0)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.harvested_losses, 0)
        self.assertEqual(result.tracking_difference, 0)
        self.assertTrue(any("2023 backtest unavailable" in warning for warning in result.warnings))

    def test_xlg_2025_is_full_year(self) -> None:
        _, _, label, warnings = backtest_coverage("XLG", 2025)

        self.assertEqual(label, "full-year")
        self.assertEqual(warnings, [])

    def test_xlg_model_comparison_recommends_best_current_default(self) -> None:
        result = compare_models(
            ModelComparisonRequest(index_symbol="XLG", years=[2023, 2024, 2025], starting_value=100_000)
        )

        self.assertEqual(result.recommended_model, "peer_basket")
        self.assertIn("current-year default", result.recommendation)
        recommended_rows = [row for row in result.rows if row.direct_index_model == result.recommended_model]
        self.assertEqual(len(recommended_rows), 3)
        self.assertTrue(all(abs(row.tracking_difference) <= 0.01 for row in recommended_rows))

    def test_backtest_respects_tlh_cap(self) -> None:
        result = run_backtest("QTOP", 2025, 100_000, [])

        self.assertLessEqual(result.tlh_trade_count, 1000)
        self.assertGreaterEqual(result.cap_remaining, 0)

    def test_executable_models_respect_tlh_cap_for_qtop(self) -> None:
        for model in EXECUTABLE_DIRECT_INDEX_MODELS:
            with self.subTest(model=model):
                result = run_backtest("QTOP", 2025, 100_000, [], direct_index_model=model)

                self.assertEqual(result.direct_index_model, model)
                self.assertLessEqual(result.tlh_trade_count, 1000)
                self.assertGreaterEqual(result.cap_remaining, 0)

    def test_backtest_tracking_difference_stays_under_one_percent(self) -> None:
        for symbol in ["XLG", "SPY", "TOPT", "QTOP"]:
            for year in [2024, 2025]:
                with self.subTest(symbol=symbol, year=year):
                    result = run_backtest(symbol, year, 100_000, [])

                    self.assertLess(abs(result.tracking_difference), 0.01)
                    self.assertLess(result.tracking_error, 0.01)

    def test_backtest_harvests_losses_without_breaking_tracking(self) -> None:
        for symbol in ["XLG", "SPY", "TOPT", "QTOP"]:
            for year in [2024, 2025]:
                with self.subTest(symbol=symbol, year=year):
                    result = run_backtest(symbol, year, 100_000, [])

                    if result.coverage_label == "full-year":
                        self.assertGreater(result.harvested_losses, 0)
                        self.assertGreater(result.tlh_trade_count, 0)
                    self.assertLess(abs(result.tracking_difference), 0.01)

    def test_2025_harvest_is_material_for_100k_account(self) -> None:
        for symbol in ["XLG", "SPY", "TOPT", "QTOP"]:
            with self.subTest(symbol=symbol):
                result = run_backtest(symbol, 2025, 100_000, [])

                self.assertGreater(result.harvested_losses, 900)
                self.assertLess(abs(result.tracking_difference), 0.01)

    def test_spy_reports_buyer_profitability(self) -> None:
        result = run_backtest("SPY", 2025, 100_000, [], estimated_tax_rate=0.35)

        self.assertTrue(result.is_profitable)
        self.assertGreater(result.portfolio_profit, 0)
        self.assertAlmostEqual(result.portfolio_profit, result.ending_value - result.starting_value, places=2)
        self.assertAlmostEqual(result.excess_profit, result.ending_value - result.benchmark_value, places=1)
        self.assertAlmostEqual(result.tax_adjusted_profit, result.tax_adjusted_ending_value - result.starting_value, places=1)
        self.assertEqual(result.beats_benchmark_after_tax, result.tax_adjusted_ending_value > result.benchmark_value)
        self.assertIn("Profitable", result.profitability_summary)

    def test_spy_tlh_modes_change_harvest_intensity(self) -> None:
        conservative = run_backtest("SPY", 2025, 100_000, [], estimated_tax_rate=0.35, tlh_mode="conservative")
        moderate = run_backtest("SPY", 2025, 100_000, [], estimated_tax_rate=0.35, tlh_mode="moderate")
        aggressive = run_backtest("SPY", 2025, 100_000, [], estimated_tax_rate=0.35, tlh_mode="aggressive")

        self.assertEqual(conservative.tlh_mode, "conservative")
        self.assertEqual(moderate.tlh_mode, "moderate")
        self.assertEqual(aggressive.tlh_mode, "aggressive")
        self.assertLessEqual(conservative.tlh_trade_count, moderate.tlh_trade_count)
        self.assertLessEqual(moderate.tlh_trade_count, aggressive.tlh_trade_count)
        self.assertLess(conservative.harvested_losses, aggressive.harvested_losses)
        self.assertLess(abs(aggressive.tracking_difference), 0.01)


if __name__ == "__main__":
    unittest.main()
