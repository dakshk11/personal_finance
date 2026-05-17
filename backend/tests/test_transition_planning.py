from datetime import date
import json
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.advisor import approve_transition_plan, create_transition_plan
from app.db.session import Base
from app.models.entities import Account, Advisor, Client, ClientConstraint, ImportedHolding, ImportedTaxLot, Organization, TransitionPlan, User
from app.schemas.common import TransitionPlanRequest
from app.services.transition_planning import build_transition_plan, dump_json


class TransitionPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_account(self):
        db = self.Session()
        user = User(email="advisor@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        org = Organization(name="Advisor Co")
        db.add(org)
        db.commit()
        db.refresh(org)
        advisor = Advisor(user_id=user.id, organization_id=org.id, display_name="Advisor")
        db.add(advisor)
        db.commit()
        db.refresh(advisor)
        client = Client(organization_id=org.id, advisor_id=advisor.id, name="Legacy Equity Client")
        db.add(client)
        db.commit()
        db.refresh(client)
        account = Account(client_id=client.id, name="Taxable legacy account", taxable=True)
        db.add(account)
        db.commit()
        db.refresh(account)
        db.add_all(
            [
                ImportedHolding(account_id=account.id, symbol="AAPL", name="Apple", sector="Information Technology", shares=120, price=180, market_value=21_600, as_of_date=date(2026, 5, 15)),
                ImportedHolding(account_id=account.id, symbol="MSFT", name="Microsoft", sector="Information Technology", shares=60, price=420, market_value=25_200, as_of_date=date(2026, 5, 15)),
                ImportedHolding(account_id=account.id, symbol="TSLA", name="Tesla", sector="Consumer Discretionary", shares=80, price=150, market_value=12_000, as_of_date=date(2026, 5, 15)),
                ImportedTaxLot(account_id=account.id, symbol="AAPL", acquisition_date=date(2021, 1, 4), shares=120, cost_basis_per_share=90),
                ImportedTaxLot(account_id=account.id, symbol="MSFT", acquisition_date=date(2024, 8, 1), shares=60, cost_basis_per_share=460),
                ImportedTaxLot(account_id=account.id, symbol="TSLA", acquisition_date=date(2025, 1, 2), shares=80, cost_basis_per_share=260),
            ]
        )
        constraint = ClientConstraint(
            client_id=client.id,
            target_index="XLG",
            annual_gains_budget=1_000,
            max_tracking_error=0.04,
            max_active_share=0.12,
            estimated_tax_rate=0.35,
            excluded_symbols_json=dump_json(["TSLA"]),
            excluded_sectors_json=dump_json([]),
            outside_accounts_complete=False,
        )
        db.add(constraint)
        db.commit()
        db.refresh(account)
        db.refresh(client)
        return db, user, client, account, constraint

    def test_transition_plan_respects_tax_budget_and_reports_tracking(self) -> None:
        db, _, _, account, constraint = self._seed_account()

        result = build_transition_plan(account, constraint, db)

        self.assertLessEqual(result.net_realized_gain, constraint.annual_gains_budget + 0.01)
        self.assertGreater(result.active_share, 0)
        self.assertGreater(result.tracking_drift, 0)
        self.assertTrue(any("Outside-account wash-sale data" in warning for warning in result.warnings))
        self.assertTrue(all(item.action in {"BUY", "SELL"} for item in result.recommendations))

    def test_transition_plan_approval_freezes_input_snapshot(self) -> None:
        db, user, client, _, _ = self._seed_account()

        plan_out = create_transition_plan(client.id, TransitionPlanRequest(objective="transition_gradually"), user, db)
        before = db.get(TransitionPlan, plan_out.id).input_snapshot_json
        approved = approve_transition_plan(plan_out.id, user, db)
        after = db.get(TransitionPlan, plan_out.id).input_snapshot_json

        self.assertEqual(approved.status, "approved")
        self.assertEqual(before, after)
        self.assertEqual(json.loads(after)["algorithm_version"], "transition-planner-v1.0")


if __name__ == "__main__":
    unittest.main()

