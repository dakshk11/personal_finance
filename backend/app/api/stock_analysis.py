import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, StockAnalysisRun, User
from app.schemas.common import (
    StockAnalysisDCFOut,
    StockAnalysisDigestOut,
    StockAnalysisFinancialRowOut,
    StockAnalysisRunOut,
    StockAnalysisRunRequest,
    StockAnalysisRunSummaryOut,
    StockAnalysisSourceOut,
    StockAnalysisValuationOut,
)
from app.services.ai_advisor import AIAdvisorConfigurationError, AIAdvisorProviderError, decrypt_api_key, is_goose_model, is_ollama_model, now_utc_naive, valid_ai_advisor_model
from app.services.stock_analysis import StockAnalysisLookupError, normalize_research_stance, resolve_stock_company, run_stock_analysis


router = APIRouter(prefix="/stock-analysis", tags=["stock-analysis"])
STOCK_ANALYSIS_REUSE_DAYS = 7


@router.post("/run", response_model=StockAnalysisRunOut)
def run_analysis(
    payload: StockAnalysisRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StockAnalysisRunOut:
    if not valid_ai_advisor_model(payload.model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported model. Use a gpt-* model or ollama:<model_name>.")
    try:
        company = resolve_stock_company(payload.query)
    except StockAnalysisLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    cached_run = _recent_cached_run(db, user, company.ticker, payload.model)
    if cached_run:
        return _run_out(
            cached_run,
            reused_from_cache=True,
            cache_message=f"Opened saved {cached_run.ticker} analysis from {cached_run.created_at.date().isoformat()}; no new tokens were used.",
        )

    api_key: str | None = None
    if not is_ollama_model(payload.model) and not is_goose_model(payload.model):
        key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before generating an equity research analysis.")
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
    try:
        run = run_stock_analysis(db, user.id, payload.query, payload.model, api_key, ollama_base_url=payload.ollama_base_url)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except StockAnalysisLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _run_out(run)


def _recent_cached_run(db: Session, user: User, ticker: str, model: str) -> StockAnalysisRun | None:
    cutoff = now_utc_naive() - timedelta(days=STOCK_ANALYSIS_REUSE_DAYS)
    return db.scalar(
        select(StockAnalysisRun)
        .where(
            StockAnalysisRun.user_id == user.id,
            StockAnalysisRun.ticker == ticker.upper().strip(),
            StockAnalysisRun.model == model,
            StockAnalysisRun.created_at >= cutoff,
        )
        .order_by(StockAnalysisRun.created_at.desc(), StockAnalysisRun.id.desc())
        .limit(1)
    )


@router.get("/runs", response_model=list[StockAnalysisRunSummaryOut])
def list_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StockAnalysisRunSummaryOut]:
    runs = db.scalars(
        select(StockAnalysisRun)
        .where(StockAnalysisRun.user_id == user.id)
        .order_by(StockAnalysisRun.created_at.desc(), StockAnalysisRun.id.desc())
        .limit(30)
    ).all()
    return [
        StockAnalysisRunSummaryOut(
            id=run.id,
            ticker=run.ticker,
            company_name=run.company_name,
            created_at=run.created_at,
            source_status=run.source_status,
            research_stance=normalize_research_stance(_json_load(run.digest_json, {}).get("research_stance")),
        )
        for run in runs
    ]


@router.get("/runs/{run_id}", response_model=StockAnalysisRunOut)
def get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StockAnalysisRunOut:
    run = db.get(StockAnalysisRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equity Research run not found")
    return _run_out(run)


def _run_out(run: StockAnalysisRun, *, reused_from_cache: bool = False, cache_message: str | None = None) -> StockAnalysisRunOut:
    snapshot = _json_load(run.financial_snapshot_json, {})
    valuation = snapshot.get("valuation") if isinstance(snapshot, dict) else {}
    valuation = valuation if isinstance(valuation, dict) else {}
    dcf = valuation.get("dcf") if isinstance(valuation.get("dcf"), dict) else {}
    digest = _json_load(run.digest_json, {})
    digest = digest if isinstance(digest, dict) else {}
    digest["research_stance"] = normalize_research_stance(digest.get("research_stance"))
    return StockAnalysisRunOut(
        id=run.id,
        query=run.query,
        ticker=run.ticker,
        company_name=run.company_name,
        sector=run.sector,
        industry=run.industry,
        model=run.model,
        reused_from_cache=reused_from_cache,
        cache_message=cache_message,
        created_at=run.created_at,
        source_status=run.source_status,
        research_stance=digest["research_stance"],
        sources=[StockAnalysisSourceOut(**source) for source in _json_load(run.source_json, []) if isinstance(source, dict)],
        financials=[
            StockAnalysisFinancialRowOut(**row)
            for row in (snapshot.get("financials", []) if isinstance(snapshot, dict) else [])
            if isinstance(row, dict)
        ],
        valuation=StockAnalysisValuationOut(
            current_price=valuation.get("current_price"),
            market_cap=valuation.get("market_cap"),
            trailing_pe=valuation.get("trailing_pe"),
            forward_pe=valuation.get("forward_pe"),
            price_to_sales=valuation.get("price_to_sales"),
            enterprise_to_ebitda=valuation.get("enterprise_to_ebitda"),
            industry_average_forward_pe=valuation.get("industry_average_forward_pe"),
            peer_average_forward_pe=valuation.get("peer_average_forward_pe"),
            dcf=StockAnalysisDCFOut(**dcf),
            peers=valuation.get("peers", []) if isinstance(valuation.get("peers"), list) else [],
        ),
        digest=StockAnalysisDigestOut(**digest),
        warnings=_json_load(run.warnings_json, []),
        usage=_json_load(run.usage_json, {}),
    )


def _json_load(value: str | None, default: object) -> object:
    if not value:
        return default
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return default
    if isinstance(default, dict):
        return loaded if isinstance(loaded, dict) else default
    if isinstance(default, list):
        return loaded if isinstance(loaded, list) else default
    return loaded
