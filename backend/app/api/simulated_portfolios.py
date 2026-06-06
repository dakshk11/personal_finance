from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import SimulatedPortfolio, SimulatedPortfolioTrade, User
from app.schemas.common import (
    SimulatedPortfolioIn,
    SimulatedPortfolioOut,
    SimulatedPortfolioPriceUpdate,
    SimulatedPortfolioTradeOut,
)

router = APIRouter(prefix="/simulated-portfolios", tags=["simulated-portfolios"])


def _trade_out(trade: SimulatedPortfolioTrade) -> SimulatedPortfolioTradeOut:
    return SimulatedPortfolioTradeOut(
        id=trade.id,
        ticker=trade.ticker,
        name=trade.name,
        sleeve=trade.sleeve,
        category=trade.category,
        yield_pct=trade.yield_pct,
        target_weight=trade.target_weight,
        target_amount=trade.target_amount,
        shares=trade.shares,
        cost_basis_per_share=trade.cost_basis_per_share,
        current_price=trade.current_price,
        purchase_date=trade.purchase_date,
        market_value=trade.market_value,
        cost_basis=trade.cost_basis,
        gain_loss=trade.gain_loss,
        return_pct=trade.return_pct,
        annual_income=trade.annual_income,
    )


def _portfolio_out(portfolio: SimulatedPortfolio) -> SimulatedPortfolioOut:
    return SimulatedPortfolioOut(
        id=portfolio.id,
        name=portfolio.name,
        cash_amount=portfolio.cash_amount,
        target_value=portfolio.target_value,
        cost_basis=portfolio.cost_basis,
        market_value=portfolio.market_value,
        gain_loss=portfolio.gain_loss,
        return_pct=portfolio.return_pct,
        annual_income=portfolio.annual_income,
        notes=portfolio.notes,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at or portfolio.created_at,
        trades=[_trade_out(trade) for trade in portfolio.trades],
    )


def _recalculate_trade(trade: SimulatedPortfolioTrade) -> None:
    trade.market_value = round(trade.shares * trade.current_price, 2)
    trade.cost_basis = round(trade.shares * trade.cost_basis_per_share, 2)
    trade.gain_loss = round(trade.market_value - trade.cost_basis, 2)
    trade.return_pct = round((trade.gain_loss / trade.cost_basis) * 100, 4) if trade.cost_basis > 0 else 0
    trade.annual_income = round(trade.market_value * (trade.yield_pct / 100), 2)


def _recalculate_portfolio(portfolio: SimulatedPortfolio) -> None:
    for trade in portfolio.trades:
        _recalculate_trade(trade)
    portfolio.cost_basis = round(sum(trade.cost_basis for trade in portfolio.trades), 2)
    portfolio.market_value = round(sum(trade.market_value for trade in portfolio.trades), 2)
    portfolio.gain_loss = round(portfolio.market_value - portfolio.cost_basis, 2)
    portfolio.return_pct = round((portfolio.gain_loss / portfolio.cost_basis) * 100, 4) if portfolio.cost_basis > 0 else 0
    portfolio.annual_income = round(sum(trade.annual_income for trade in portfolio.trades), 2)


@router.get("", response_model=list[SimulatedPortfolioOut])
def list_simulated_portfolios(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SimulatedPortfolioOut]:
    rows = db.scalars(
        select(SimulatedPortfolio)
        .where(SimulatedPortfolio.user_id == user.id)
        .order_by(SimulatedPortfolio.created_at.desc(), SimulatedPortfolio.id.desc())
    ).all()
    return [_portfolio_out(row) for row in rows]


@router.post("", response_model=SimulatedPortfolioOut, status_code=status.HTTP_201_CREATED)
def create_simulated_portfolio(
    payload: SimulatedPortfolioIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SimulatedPortfolioOut:
    portfolio = SimulatedPortfolio(
        user_id=user.id,
        name=payload.name,
        cash_amount=payload.cash_amount,
        target_value=payload.target_value,
        notes=payload.notes,
    )
    for item in payload.trades:
        portfolio.trades.append(SimulatedPortfolioTrade(
            ticker=item.ticker.upper(),
            name=item.name,
            sleeve=str(item.sleeve),
            category=item.category,
            yield_pct=item.yield_pct,
            target_weight=item.target_weight,
            target_amount=item.target_amount,
            shares=item.shares,
            cost_basis_per_share=item.cost_basis_per_share,
            current_price=item.current_price,
            purchase_date=item.purchase_date,
        ))
    _recalculate_portfolio(portfolio)
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return _portfolio_out(portfolio)


@router.patch("/{portfolio_id}/prices", response_model=SimulatedPortfolioOut)
def update_simulated_portfolio_prices(
    portfolio_id: int,
    payload: SimulatedPortfolioPriceUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SimulatedPortfolioOut:
    portfolio = db.scalar(
        select(SimulatedPortfolio)
        .where(SimulatedPortfolio.id == portfolio_id)
        .where(SimulatedPortfolio.user_id == user.id)
    )
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Simulated portfolio not found")

    prices = {item.ticker.upper(): item.current_price for item in payload.prices}
    for trade in portfolio.trades:
        if trade.ticker.upper() in prices:
            trade.current_price = prices[trade.ticker.upper()]

    _recalculate_portfolio(portfolio)
    db.commit()
    db.refresh(portfolio)
    return _portfolio_out(portfolio)
