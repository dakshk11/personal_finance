from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Portfolio, PortfolioExclusion, TaxLot, Trade, User
from app.schemas.common import (
    ExclusionIn,
    GenerateTradesRequest,
    PortfolioInitializationOut,
    PortfolioInitializationRequest,
    PortfolioCreate,
    PortfolioImportOut,
    PortfolioImportRequest,
    PortfolioOut,
    TradeGenerationOut,
    TradeOut,
)
from app.services.direct_indexing import Position, calculate_tracking_metrics, choose_replacements, generate_rebalance_trades, normalize_holdings
from app.services.direct_index_models import direct_index_model_config
from app.services.market_data import get_prices, holdings_for_index
from app.services.tax_loss import ANNUAL_TLH_TRADE_CAP, PriorTrade, TaxLotInput, generate_tax_loss_harvest_trades


router = APIRouter(prefix="/portfolios", tags=["portfolios"])


def _portfolio_out(portfolio: Portfolio) -> PortfolioOut:
    return PortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        index_symbol=portfolio.index_symbol,
        starting_value=portfolio.starting_value,
        cash=portfolio.cash,
        exclusions=[item.symbol for item in portfolio.exclusions],
    )


def _get_portfolio(db: Session, user: User, portfolio_id: int) -> Portfolio:
    portfolio = db.get(Portfolio, portfolio_id)
    if not portfolio or portfolio.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return portfolio


def _last_business_day(today: date | None = None) -> date:
    current = today or date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _trade_replacements(holdings, exclusions: set[str], index_symbol: str, direct_index_model: str) -> dict[str, str]:
    model = direct_index_model_config(direct_index_model)
    if model.id == "completion_etf":
        return {holding.symbol: index_symbol for holding in holdings if holding.symbol != index_symbol}
    return choose_replacements(holdings, exclusions)


def _trade_loss_overrides(direct_index_model: str) -> tuple[float | None, float | None]:
    model = direct_index_model_config(direct_index_model)
    return model.min_loss_percent, model.min_loss_dollars


def _apply_simulated_trade(db: Session, portfolio: Portfolio, recommendation: TradeOut) -> float:
    realized_gain_loss = 0.0
    if recommendation.action == "BUY":
        db.add(
            TaxLot(
                portfolio_id=portfolio.id,
                symbol=recommendation.symbol,
                acquisition_date=recommendation.trade_date,
                shares=recommendation.shares,
                cost_basis_per_share=recommendation.price,
                is_open=True,
            )
        )
        portfolio.cash -= recommendation.notional
        return realized_gain_loss

    shares_to_sell = recommendation.shares
    lots = db.scalars(
        select(TaxLot)
        .where(TaxLot.portfolio_id == portfolio.id, TaxLot.symbol == recommendation.symbol, TaxLot.is_open.is_(True))
        .order_by(TaxLot.acquisition_date.asc(), TaxLot.id.asc())
    ).all()
    for lot in lots:
        if shares_to_sell <= 0:
            break
        sold_shares = min(lot.shares, shares_to_sell)
        realized_gain_loss += sold_shares * (recommendation.price - lot.cost_basis_per_share)
        lot.shares -= sold_shares
        shares_to_sell -= sold_shares
        if lot.shares <= 0.000001:
            lot.is_open = False
        db.add(lot)
    portfolio.cash += recommendation.notional
    return round(realized_gain_loss, 2)


def _preview_realized_gain_loss(
    lot_state: dict[str, list[tuple[float, float]]],
    recommendation: TradeOut,
) -> float:
    if recommendation.action == "BUY":
        lot_state.setdefault(recommendation.symbol, []).append((recommendation.shares, recommendation.price))
        return 0

    realized_gain_loss = 0.0
    shares_to_sell = recommendation.shares
    lots = lot_state.get(recommendation.symbol, [])
    remaining_lots: list[tuple[float, float]] = []
    for shares, basis in lots:
        if shares_to_sell <= 0:
            remaining_lots.append((shares, basis))
            continue
        sold_shares = min(shares, shares_to_sell)
        realized_gain_loss += sold_shares * (recommendation.price - basis)
        shares_to_sell -= sold_shares
        remaining_shares = shares - sold_shares
        if remaining_shares > 0.000001:
            remaining_lots.append((remaining_shares, basis))
    lot_state[recommendation.symbol] = remaining_lots
    return round(realized_gain_loss, 2)


def _build_trade_generation(
    db: Session,
    portfolio: Portfolio,
    payload: GenerateTradesRequest,
    mutate: bool,
) -> TradeGenerationOut:
    model = direct_index_model_config(payload.direct_index_model)
    trade_date = payload.as_of_date or _last_business_day()
    exclusions = {item.symbol for item in portfolio.exclusions}
    holdings = normalize_holdings(holdings_for_index(portfolio.index_symbol), exclusions)
    tax_lots = db.scalars(select(TaxLot).where(TaxLot.portfolio_id == portfolio.id, TaxLot.is_open.is_(True))).all()
    replacements = _trade_replacements(holdings, exclusions, portfolio.index_symbol, model.id)
    symbols = sorted({holding.symbol for holding in holdings} | {lot.symbol for lot in tax_lots} | set(replacements.values()))
    prices = get_prices(db, symbols, trade_date)

    positions = [
        Position(symbol=lot.symbol, shares=lot.shares, price=prices.get(lot.symbol, lot.cost_basis_per_share))
        for lot in tax_lots
    ]
    current_value = sum(position.market_value for position in positions) + portfolio.cash
    portfolio_value = current_value if current_value > 0 else portfolio.starting_value

    rebalance = generate_rebalance_trades(
        trade_date=trade_date,
        holdings=holdings,
        positions=positions,
        prices=prices,
        portfolio_value=portfolio_value,
        exclusions=exclusions,
    )

    prior_trade_rows = db.scalars(select(Trade).where(Trade.portfolio_id == portfolio.id)).all()
    prior_trades = [
        PriorTrade(trade_date=row.trade_date, action=row.action, symbol=row.symbol, shares=row.shares)
        for row in prior_trade_rows
    ]
    annual_tlh_count = db.scalar(
        select(func.count(Trade.id)).where(
            Trade.portfolio_id == portfolio.id,
            Trade.reason.in_(["tax_loss_harvest", "tax_loss_replacement"]),
            Trade.trade_date >= date(trade_date.year, 1, 1),
            Trade.trade_date <= date(trade_date.year, 12, 31),
        )
    ) or 0

    lot_inputs = [
        TaxLotInput(
            symbol=lot.symbol,
            acquisition_date=lot.acquisition_date,
            shares=lot.shares,
            cost_basis_per_share=lot.cost_basis_per_share,
        )
        for lot in tax_lots
    ]
    min_loss_percent, min_loss_dollars = _trade_loss_overrides(model.id)
    tlh = generate_tax_loss_harvest_trades(
        trade_date=trade_date,
        lots=lot_inputs,
        prices=prices,
        replacements=replacements,
        prior_trades=prior_trades,
        annual_trade_count=int(annual_tlh_count),
        annual_trade_cap=ANNUAL_TLH_TRADE_CAP,
        min_loss_percent=min_loss_percent,
        min_loss_dollars=min_loss_dollars,
        tlh_mode=payload.tlh_mode,
    ) if payload.enable_tlh else None

    recommendations: list[TradeOut] = [
        TradeOut(
            trade_date=trade.trade_date,
            action=trade.action,
            symbol=trade.symbol,
            shares=trade.shares,
            price=trade.price,
            notional=trade.notional,
            reason=trade.reason,
            tracking_impact=trade.tracking_impact,
            notes=trade.notes,
        )
        for trade in rebalance
    ]
    if tlh:
        recommendations.extend(
            TradeOut(
                trade_date=trade.trade_date,
                action=trade.action,
                symbol=trade.symbol,
                shares=trade.shares,
                price=trade.price,
                notional=trade.notional,
                reason=trade.reason,
                harvested_loss=trade.harvested_loss,
                wash_sale_status=trade.wash_sale_status,
                notes=trade.notes,
            )
            for trade in tlh.trades
        )

    if mutate:
        for recommendation in recommendations:
            recommendation.realized_gain_loss = _apply_simulated_trade(db, portfolio, recommendation)
            db.add(
                Trade(
                    portfolio_id=portfolio.id,
                    trade_date=recommendation.trade_date,
                    action=recommendation.action,
                    symbol=recommendation.symbol,
                    shares=recommendation.shares,
                    price=recommendation.price,
                    notional=recommendation.notional,
                    reason=recommendation.reason,
                    index_symbol=portfolio.index_symbol,
                    realized_gain_loss=recommendation.realized_gain_loss,
                    harvested_loss=recommendation.harvested_loss,
                    tracking_impact=recommendation.tracking_impact,
                    wash_sale_status=recommendation.wash_sale_status,
                    notes=recommendation.notes,
                )
            )
        db.add(portfolio)
        db.commit()
    else:
        lot_state = {
            lot.symbol: [(row.shares, row.cost_basis_per_share) for row in tax_lots if row.symbol == lot.symbol]
            for lot in tax_lots
        }
        for recommendation in recommendations:
            recommendation.realized_gain_loss = _preview_realized_gain_loss(lot_state, recommendation)

    tracking = calculate_tracking_metrics(holdings, positions, portfolio.cash, exclusions)
    warnings = list(tlh.warnings if tlh else [])
    if not mutate:
        warnings.append("Preview only; no tax lots, cash, or trade records were changed.")
    return TradeGenerationOut(
        tlh_mode=payload.tlh_mode,
        direct_index_model=model.id,
        trades=recommendations[:1000],
        tracking_score=tracking.tracking_score,
        tracking_difference=tracking.tracking_difference,
        cap_used=tlh.cap_used if tlh else int(annual_tlh_count),
        cap_remaining=tlh.cap_remaining if tlh else max(0, ANNUAL_TLH_TRADE_CAP - int(annual_tlh_count)),
        dropped_tlh_candidates=len(tlh.dropped_candidates) if tlh else 0,
        skipped_tax_loss_value=tlh.skipped_tax_loss_value if tlh else 0,
        warnings=warnings,
    )


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[PortfolioOut]:
    portfolios = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.created_at.desc())).all()
    return [_portfolio_out(portfolio) for portfolio in portfolios]


@router.post("", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def create_portfolio(payload: PortfolioCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PortfolioOut:
    portfolio = Portfolio(
        user_id=user.id,
        name=payload.name,
        index_symbol=payload.index_symbol.upper(),
        starting_value=payload.starting_value,
        cash=payload.starting_value,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return _portfolio_out(portfolio)


@router.post("/import", response_model=PortfolioImportOut, status_code=status.HTTP_201_CREATED)
def import_portfolio(payload: PortfolioImportRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PortfolioImportOut:
    if not payload.holdings and not payload.tax_lots:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import requires at least one holding or tax lot")

    warnings: list[str] = []
    default_date = _last_business_day()
    holding_values = [
        holding.market_value if holding.market_value is not None else holding.shares * holding.price
        for holding in payload.holdings
    ]
    imported_value = round(sum(holding_values), 2)
    if imported_value <= 0:
        imported_value = round(sum(lot.shares * lot.cost_basis_per_share for lot in payload.tax_lots), 2)
        warnings.append("No market values were supplied; portfolio value used tax-lot cost basis.")
    if not payload.tax_lots:
        warnings.append("No tax lots supplied; imported holdings were opened at current price as cost basis.")

    portfolio = Portfolio(
        user_id=user.id,
        name=payload.name,
        index_symbol=payload.index_symbol.upper().strip().replace("/", "."),
        starting_value=round(imported_value + payload.cash, 2),
        cash=round(payload.cash, 2),
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    tax_lot_count = 0
    if payload.tax_lots:
        for lot in payload.tax_lots:
            db.add(
                TaxLot(
                    portfolio_id=portfolio.id,
                    symbol=lot.symbol.upper().strip().replace("/", "."),
                    acquisition_date=lot.acquisition_date,
                    shares=lot.shares,
                    cost_basis_per_share=lot.cost_basis_per_share,
                    is_open=True,
                )
            )
            tax_lot_count += 1
    else:
        for holding in payload.holdings:
            db.add(
                TaxLot(
                    portfolio_id=portfolio.id,
                    symbol=holding.symbol.upper().strip().replace("/", "."),
                    acquisition_date=holding.as_of_date or default_date,
                    shares=holding.shares,
                    cost_basis_per_share=holding.price,
                    is_open=True,
                )
            )
            tax_lot_count += 1

    db.commit()
    db.refresh(portfolio)
    return PortfolioImportOut(
        portfolio=_portfolio_out(portfolio),
        imported_positions=len(payload.holdings),
        imported_tax_lots=tax_lot_count,
        imported_value=imported_value,
        warnings=warnings,
    )


@router.post("/{portfolio_id}/exclusions", response_model=PortfolioOut)
def add_exclusion(portfolio_id: int, payload: ExclusionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PortfolioOut:
    portfolio = _get_portfolio(db, user, portfolio_id)
    symbol = payload.symbol.upper().strip().replace("/", ".")
    existing = db.scalar(select(PortfolioExclusion).where(PortfolioExclusion.portfolio_id == portfolio.id, PortfolioExclusion.symbol == symbol))
    if not existing:
        db.add(PortfolioExclusion(portfolio_id=portfolio.id, symbol=symbol, reason=payload.reason))
        db.commit()
        db.refresh(portfolio)
    return _portfolio_out(portfolio)


@router.delete("/{portfolio_id}/exclusions/{symbol}", response_model=PortfolioOut)
def remove_exclusion(portfolio_id: int, symbol: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> PortfolioOut:
    portfolio = _get_portfolio(db, user, portfolio_id)
    normalized = symbol.upper().strip().replace("/", ".")
    exclusion = db.scalar(select(PortfolioExclusion).where(PortfolioExclusion.portfolio_id == portfolio.id, PortfolioExclusion.symbol == normalized))
    if exclusion:
        db.delete(exclusion)
        db.commit()
        db.refresh(portfolio)
    return _portfolio_out(portfolio)


@router.post("/{portfolio_id}/initialize-current", response_model=PortfolioInitializationOut)
def initialize_current_portfolio(
    portfolio_id: int,
    payload: PortfolioInitializationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioInitializationOut:
    portfolio = _get_portfolio(db, user, portfolio_id)
    open_lot_count = db.scalar(select(func.count(TaxLot.id)).where(TaxLot.portfolio_id == portfolio.id, TaxLot.is_open.is_(True))) or 0
    trade_count = db.scalar(select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id)) or 0
    if open_lot_count or trade_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Portfolio already has open tax lots or trades; current initialization would overwrite history.",
        )

    as_of_date = payload.as_of_date or _last_business_day()
    exclusions = {item.symbol for item in portfolio.exclusions}
    holdings = normalize_holdings(holdings_for_index(portfolio.index_symbol), exclusions)
    prices = get_prices(db, [holding.symbol for holding in holdings], as_of_date)
    invested_value = 0.0
    for holding in holdings:
        target_value = portfolio.starting_value * holding.weight
        price = prices[holding.symbol]
        shares = target_value / price
        invested_value += target_value
        db.add(
            TaxLot(
                portfolio_id=portfolio.id,
                symbol=holding.symbol,
                acquisition_date=as_of_date,
                shares=shares,
                cost_basis_per_share=price,
                is_open=True,
            )
        )
        db.add(
            Trade(
                portfolio_id=portfolio.id,
                trade_date=as_of_date,
                action="BUY",
                symbol=holding.symbol,
                shares=round(shares, 6),
                price=round(price, 4),
                notional=round(target_value, 2),
                reason="initial_current_position",
                index_symbol=portfolio.index_symbol,
                notes="Seeded current direct-index portfolio from latest cached holdings and prices.",
            )
        )
    portfolio.cash = round(portfolio.starting_value - invested_value, 2)
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return PortfolioInitializationOut(
        portfolio=_portfolio_out(portfolio),
        as_of_date=as_of_date,
        seeded_positions=len(holdings),
        invested_value=round(invested_value, 2),
        warnings=["Current portfolio seeded from cached holdings and deterministic fallback prices when provider data is unavailable."],
    )


@router.post("/{portfolio_id}/trades/preview", response_model=TradeGenerationOut)
def preview_trades(
    portfolio_id: int,
    payload: GenerateTradesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TradeGenerationOut:
    portfolio = _get_portfolio(db, user, portfolio_id)
    return _build_trade_generation(db, portfolio, payload, mutate=False)


@router.post("/{portfolio_id}/trades/generate", response_model=TradeGenerationOut)
def generate_trades(
    portfolio_id: int,
    payload: GenerateTradesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TradeGenerationOut:
    portfolio = _get_portfolio(db, user, portfolio_id)
    return _build_trade_generation(db, portfolio, payload, mutate=True)
