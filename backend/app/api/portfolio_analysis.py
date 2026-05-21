from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import PortfolioAnalyzerOut, PortfolioAnalyzerRequest
from app.services.portfolio_analysis import analyze_portfolio_holdings


router = APIRouter(prefix="/portfolio-analysis", tags=["portfolio-analysis"])


@router.post("/analyze", response_model=PortfolioAnalyzerOut)
def analyze_portfolio(
    payload: PortfolioAnalyzerRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioAnalyzerOut:
    if not payload.holdings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Add at least one portfolio holding.")
    return analyze_portfolio_holdings(
        db,
        payload.holdings,
        min_weight_percent=payload.min_weight_percent,
        as_of_date=payload.as_of_date,
    )
