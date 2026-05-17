from datetime import UTC, date, datetime
import csv
from io import StringIO
import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import (
    Account,
    Advisor,
    Client,
    ClientConstraint,
    EquivalentSecurityGroup,
    ImportedHolding,
    ImportedTaxLot,
    Organization,
    Proposal,
    RecommendationAuditEvent,
    TransitionPlan,
    User,
)
from app.schemas.common import (
    AccountImportRequest,
    AccountOut,
    AdvisorClientCreate,
    AdvisorClientOut,
    ClientConstraintIn,
    ClientConstraintOut,
    EquivalentSecurityGroupIn,
    ImportedHoldingOut,
    ImportedTaxLotOut,
    TransitionPlanOut,
    TransitionPlanRequest,
    TransitionRecommendationOut,
)
from app.services.transition_planning import (
    ALGORITHM_VERSION,
    LEGAL_DISCLAIMER_WARNINGS,
    build_transition_plan,
    dump_json,
    load_json_list,
    normalize_symbol,
)


router = APIRouter(tags=["advisor"])


def _advisor_for_user(db: Session, user: User) -> Advisor:
    advisor = db.scalar(select(Advisor).where(Advisor.user_id == user.id))
    if advisor:
        return advisor
    organization = Organization(name=f"{user.email.split('@')[0]} advisory")
    db.add(organization)
    db.commit()
    db.refresh(organization)
    advisor = Advisor(user_id=user.id, organization_id=organization.id, display_name=user.email)
    db.add(advisor)
    db.commit()
    db.refresh(advisor)
    return advisor


def _get_client(db: Session, advisor: Advisor, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if not client or client.advisor_id != advisor.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _get_account(client: Client, account_id: int | None = None) -> Account:
    if account_id is None:
        if not client.accounts:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client has no imported account")
        return max(client.accounts, key=lambda account: account.imported_at)
    for account in client.accounts:
        if account.id == account_id:
            return account
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


def _latest_constraint(db: Session, client: Client) -> ClientConstraint:
    constraint = db.scalar(
        select(ClientConstraint)
        .where(ClientConstraint.client_id == client.id)
        .order_by(ClientConstraint.created_at.desc(), ClientConstraint.id.desc())
    )
    if constraint:
        return constraint
    constraint = ClientConstraint(client_id=client.id)
    db.add(constraint)
    db.commit()
    db.refresh(constraint)
    return constraint


def _get_plan(db: Session, advisor: Advisor, plan_id: int) -> TransitionPlan:
    plan = db.get(TransitionPlan, plan_id)
    if not plan or plan.proposal.advisor_id != advisor.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition plan not found")
    return plan


def _account_out(account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        client_id=account.client_id,
        name=account.name,
        account_type=account.account_type,
        taxable=account.taxable,
        custodian=account.custodian,
        imported_at=account.imported_at,
        holdings=[
            ImportedHoldingOut(
                symbol=row.symbol,
                name=row.name,
                sector=row.sector,
                shares=row.shares,
                price=row.price,
                market_value=row.market_value,
                as_of_date=row.as_of_date,
            )
            for row in sorted(account.holdings, key=lambda item: item.symbol)
        ],
        tax_lots=[
            ImportedTaxLotOut(
                symbol=row.symbol,
                acquisition_date=row.acquisition_date,
                shares=row.shares,
                cost_basis_per_share=row.cost_basis_per_share,
            )
            for row in sorted(account.tax_lots, key=lambda item: (item.symbol, item.acquisition_date))
        ],
    )


def _constraint_out(client: Client, constraint: ClientConstraint) -> ClientConstraintOut:
    return ClientConstraintOut(
        id=constraint.id,
        target_index=constraint.target_index,
        annual_gains_budget=constraint.annual_gains_budget,
        max_tracking_error=constraint.max_tracking_error,
        max_active_share=constraint.max_active_share,
        estimated_tax_rate=constraint.estimated_tax_rate,
        excluded_symbols=load_json_list(constraint.excluded_symbols_json),
        excluded_sectors=load_json_list(constraint.excluded_sectors_json),
        household_wash_sale_notes=constraint.household_wash_sale_notes,
        outside_accounts_complete=constraint.outside_accounts_complete,
        equivalent_groups=[
            EquivalentSecurityGroupIn(name=group.name, symbols=load_json_list(group.symbols_json))
            for group in client.equivalent_groups
        ],
        created_at=constraint.created_at,
    )


def _recommendations_from_json(value: str) -> list[TransitionRecommendationOut]:
    rows = json.loads(value or "[]")
    return [TransitionRecommendationOut(**row) for row in rows]


def _plan_out(plan: TransitionPlan) -> TransitionPlanOut:
    proposal = plan.proposal
    return TransitionPlanOut(
        id=plan.id,
        proposal_id=proposal.id,
        client_id=proposal.client_id,
        client_name=proposal.client.name,
        account_id=plan.account_id,
        account_name=plan.account.name if plan.account else None,
        title=proposal.title,
        status=proposal.status,
        objective=plan.objective,
        algorithm_version=plan.algorithm_version,
        target_index=plan.target_index,
        data_source_summary=plan.data_source_summary,
        portfolio_value=plan.portfolio_value,
        target_value=plan.target_value,
        realized_gains=plan.realized_gains,
        realized_losses=plan.realized_losses,
        net_realized_gain=plan.net_realized_gain,
        estimated_tax_impact=plan.estimated_tax_impact,
        tracking_drift=plan.tracking_drift,
        active_share=plan.active_share,
        turnover=plan.turnover,
        skipped_trade_count=plan.skipped_trade_count,
        warnings=json.loads(plan.warnings_json or "[]"),
        recommendations=_recommendations_from_json(plan.recommendations_json),
        input_snapshot=json.loads(plan.input_snapshot_json or "{}"),
        created_at=plan.created_at,
    )


@router.post("/advisor/clients", response_model=AdvisorClientOut, status_code=status.HTTP_201_CREATED)
def create_advisor_client(
    payload: AdvisorClientCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    advisor = _advisor_for_user(db, user)
    client = Client(
        organization_id=advisor.organization_id,
        advisor_id=advisor.id,
        name=payload.name.strip(),
        email=payload.email.strip().lower() if payload.email else None,
        household_notes=payload.household_notes,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/advisor/clients", response_model=list[AdvisorClientOut])
def list_advisor_clients(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Client]:
    advisor = _advisor_for_user(db, user)
    return db.scalars(select(Client).where(Client.advisor_id == advisor.id).order_by(Client.created_at.desc())).all()


@router.post("/clients/{client_id}/accounts/import", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def import_client_account(
    client_id: int,
    payload: AccountImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountOut:
    advisor = _advisor_for_user(db, user)
    client = _get_client(db, advisor, client_id)
    if not payload.holdings and not payload.tax_lots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import requires at least one holding or tax lot")
    account = Account(
        client_id=client.id,
        name=payload.account_name,
        account_type=payload.account_type,
        taxable=payload.taxable,
        custodian=payload.custodian,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    default_date = date.today()
    for holding in payload.holdings:
        symbol = normalize_symbol(holding.symbol)
        market_value = holding.market_value if holding.market_value is not None else holding.shares * holding.price
        db.add(
            ImportedHolding(
                account_id=account.id,
                symbol=symbol,
                name=holding.name or symbol,
                sector=holding.sector,
                shares=holding.shares,
                price=holding.price,
                market_value=round(market_value, 2),
                as_of_date=holding.as_of_date or default_date,
            )
        )
    for lot in payload.tax_lots:
        db.add(
            ImportedTaxLot(
                account_id=account.id,
                symbol=normalize_symbol(lot.symbol),
                acquisition_date=lot.acquisition_date,
                shares=lot.shares,
                cost_basis_per_share=lot.cost_basis_per_share,
            )
        )
    db.commit()
    db.refresh(account)
    return _account_out(account)


@router.post("/clients/{client_id}/constraints", response_model=ClientConstraintOut, status_code=status.HTTP_201_CREATED)
def create_client_constraints(
    client_id: int,
    payload: ClientConstraintIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientConstraintOut:
    advisor = _advisor_for_user(db, user)
    client = _get_client(db, advisor, client_id)
    for existing in list(client.equivalent_groups):
        db.delete(existing)
    for group in payload.equivalent_groups:
        symbols = sorted({normalize_symbol(symbol) for symbol in group.symbols})
        if len(symbols) >= 2:
            db.add(EquivalentSecurityGroup(client_id=client.id, name=group.name, symbols_json=dump_json(symbols)))
    constraint = ClientConstraint(
        client_id=client.id,
        target_index=normalize_symbol(payload.target_index),
        annual_gains_budget=payload.annual_gains_budget,
        max_tracking_error=payload.max_tracking_error,
        max_active_share=payload.max_active_share,
        estimated_tax_rate=payload.estimated_tax_rate,
        excluded_symbols_json=dump_json(sorted({normalize_symbol(symbol) for symbol in payload.excluded_symbols})),
        excluded_sectors_json=dump_json(sorted({sector.strip() for sector in payload.excluded_sectors if sector.strip()})),
        household_wash_sale_notes=payload.household_wash_sale_notes,
        outside_accounts_complete=payload.outside_accounts_complete,
    )
    db.add(constraint)
    db.commit()
    db.refresh(client)
    db.refresh(constraint)
    return _constraint_out(client, constraint)


@router.post("/clients/{client_id}/transition-plans", response_model=TransitionPlanOut, status_code=status.HTTP_201_CREATED)
def create_transition_plan(
    client_id: int,
    payload: TransitionPlanRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransitionPlanOut:
    advisor = _advisor_for_user(db, user)
    client = _get_client(db, advisor, client_id)
    account = _get_account(client, payload.account_id)
    constraint = _latest_constraint(db, client)
    computation = build_transition_plan(account, constraint, db, payload.objective)
    proposal = Proposal(
        client_id=client.id,
        advisor_id=advisor.id,
        title=payload.title or f"{client.name} transition proposal",
        status="draft",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    plan = TransitionPlan(
        proposal_id=proposal.id,
        account_id=account.id,
        algorithm_version=ALGORITHM_VERSION,
        target_index=constraint.target_index,
        status="draft",
        objective=payload.objective,
        input_snapshot_json=dump_json(computation.input_snapshot),
        recommendations_json=dump_json([item.__dict__ for item in computation.recommendations]),
        warnings_json=dump_json(computation.warnings),
        data_source_summary=computation.data_source_summary,
        portfolio_value=computation.portfolio_value,
        target_value=computation.target_value,
        realized_gains=computation.realized_gains,
        realized_losses=computation.realized_losses,
        net_realized_gain=computation.net_realized_gain,
        estimated_tax_impact=computation.estimated_tax_impact,
        tracking_drift=computation.tracking_drift,
        active_share=computation.active_share,
        turnover=computation.turnover,
        skipped_trade_count=computation.skipped_trade_count,
    )
    db.add(plan)
    db.add(
        RecommendationAuditEvent(
            proposal_id=proposal.id,
            event_type="created",
            actor_user_id=user.id,
            details_json=dump_json({"algorithm_version": ALGORITHM_VERSION, "objective": payload.objective}),
        )
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.get("/transition-plans/{plan_id}", response_model=TransitionPlanOut)
def get_transition_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransitionPlanOut:
    advisor = _advisor_for_user(db, user)
    plan = _get_plan(db, advisor, plan_id)
    return _plan_out(plan)


@router.post("/transition-plans/{plan_id}/approve", response_model=TransitionPlanOut)
def approve_transition_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransitionPlanOut:
    advisor = _advisor_for_user(db, user)
    plan = _get_plan(db, advisor, plan_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    plan.status = "approved"
    plan.approved_at = now
    plan.proposal.status = "approved"
    plan.proposal.reviewed_at = plan.proposal.reviewed_at or now
    plan.proposal.approved_at = now
    db.add(plan)
    db.add(plan.proposal)
    db.add(
        RecommendationAuditEvent(
            proposal_id=plan.proposal_id,
            transition_plan_id=plan.id,
            event_type="approved",
            actor_user_id=user.id,
            details_json=dump_json({"approved_at": now.isoformat(), "input_snapshot_frozen": True}),
        )
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.get("/transition-plans/{plan_id}/export.csv")
def export_transition_plan_csv(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    advisor = _advisor_for_user(db, user)
    plan = _get_plan(db, advisor, plan_id)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["DirectIndex advisor transition proposal"])
    writer.writerow(["Proposal", plan.proposal.title])
    writer.writerow(["Client", plan.proposal.client.name])
    writer.writerow(["Status", plan.proposal.status])
    writer.writerow(["Algorithm version", plan.algorithm_version])
    writer.writerow(["Target index", plan.target_index])
    writer.writerow(["Data sources", plan.data_source_summary])
    writer.writerow([])
    writer.writerow(["Legal disclaimer"])
    for disclaimer in LEGAL_DISCLAIMER_WARNINGS:
        writer.writerow([disclaimer])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    for label, value in [
        ("Portfolio value", plan.portfolio_value),
        ("Realized gains", plan.realized_gains),
        ("Realized losses", plan.realized_losses),
        ("Net realized gain", plan.net_realized_gain),
        ("Estimated tax impact", plan.estimated_tax_impact),
        ("Tracking drift", plan.tracking_drift),
        ("Active share", plan.active_share),
        ("Turnover", plan.turnover),
        ("Skipped trades", plan.skipped_trade_count),
    ]:
        writer.writerow([label, value])
    writer.writerow([])
    writer.writerow(["Warnings"])
    for warning in json.loads(plan.warnings_json or "[]"):
        writer.writerow([warning])
    writer.writerow([])
    writer.writerow(["Stage", "Action", "Symbol", "Shares", "Price", "Notional", "Realized gain/loss", "Tax impact", "Reason", "Wash sale", "Notes"])
    for row in json.loads(plan.recommendations_json or "[]"):
        writer.writerow([
            row["stage"],
            row["action"],
            row["symbol"],
            row["shares"],
            row["price"],
            row["notional"],
            row["realized_gain_loss"],
            row["estimated_tax_impact"],
            row["reason"],
            row["wash_sale_status"],
            row["notes"],
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="transition-plan-{plan.id}.csv"'},
    )
