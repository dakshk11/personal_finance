from datetime import date
import unittest

from app.services.tax_loss import (
    ANNUAL_TLH_TRADE_CAP,
    PriorTrade,
    TaxLotInput,
    generate_tax_loss_harvest_trades,
    replacement_is_substantially_identical,
    violates_wash_sale,
)


class TaxLossHarvestingTests(unittest.TestCase):
    def test_wash_sale_blocks_prior_buy_inside_window(self) -> None:
        blocked = violates_wash_sale(
            sold_symbol="AAPL",
            sale_date=date(2025, 5, 15),
            prior_trades=[PriorTrade(trade_date=date(2025, 5, 1), action="BUY", symbol="AAPL", shares=1)],
        )

        self.assertTrue(blocked)

    def test_equivalent_group_replacement_is_substantially_identical(self) -> None:
        self.assertTrue(
            replacement_is_substantially_identical(
                "GOOG",
                "GOOGL",
                equivalent_groups=[{"GOOG", "GOOGL"}],
            )
        )

    def test_annual_trade_cap_never_exceeds_1000_and_prioritizes_tax_impact(self) -> None:
        lots = [
            TaxLotInput(
                symbol=f"LOSS{i}",
                acquisition_date=date(2024, 1, 2),
                shares=10,
                cost_basis_per_share=200 + i,
            )
            for i in range(700)
        ]
        prices = {f"LOSS{i}": 100 for i in range(700)}
        prices.update({f"REPL{i}": 100 for i in range(700)})
        replacements = {f"LOSS{i}": f"REPL{i}" for i in range(700)}

        result = generate_tax_loss_harvest_trades(
            trade_date=date(2025, 12, 1),
            lots=lots,
            prices=prices,
            replacements=replacements,
        )

        self.assertEqual(len(result.trades), ANNUAL_TLH_TRADE_CAP)
        self.assertEqual(result.cap_remaining, 0)
        harvested_sell_symbols = {trade.symbol for trade in result.trades if trade.action == "SELL"}
        self.assertIn("LOSS699", harvested_sell_symbols)
        self.assertNotIn("LOSS0", harvested_sell_symbols)
        self.assertGreater(result.skipped_tax_loss_value, 0)

    def test_existing_annual_count_reduces_remaining_capacity(self) -> None:
        lots = [
            TaxLotInput(symbol="AAPL", acquisition_date=date(2024, 1, 2), shares=10, cost_basis_per_share=200),
            TaxLotInput(symbol="MSFT", acquisition_date=date(2024, 1, 2), shares=10, cost_basis_per_share=200),
        ]
        result = generate_tax_loss_harvest_trades(
            trade_date=date(2025, 12, 1),
            lots=lots,
            prices={"AAPL": 100, "MSFT": 100, "NVDA": 100, "AVGO": 100},
            replacements={"AAPL": "NVDA", "MSFT": "AVGO"},
            annual_trade_count=998,
        )

        self.assertEqual(len(result.trades), 2)
        self.assertEqual(result.cap_used, 1000)
        self.assertEqual(result.cap_remaining, 0)

    def test_tlh_modes_apply_different_loss_thresholds(self) -> None:
        lots = [
            TaxLotInput(symbol="SMALL", acquisition_date=date(2024, 1, 2), shares=10, cost_basis_per_share=105),
            TaxLotInput(symbol="LARGE", acquisition_date=date(2024, 1, 2), shares=10, cost_basis_per_share=130),
        ]
        prices = {"SMALL": 100, "LARGE": 100, "SMALLR": 100, "LARGER": 100}
        replacements = {"SMALL": "SMALLR", "LARGE": "LARGER"}

        conservative = generate_tax_loss_harvest_trades(
            trade_date=date(2025, 12, 1),
            lots=lots,
            prices=prices,
            replacements=replacements,
            tlh_mode="conservative",
        )
        aggressive = generate_tax_loss_harvest_trades(
            trade_date=date(2025, 12, 1),
            lots=lots,
            prices=prices,
            replacements=replacements,
            tlh_mode="aggressive",
        )

        self.assertEqual(len(conservative.trades), 2)
        self.assertEqual(len(aggressive.trades), 4)


if __name__ == "__main__":
    unittest.main()
