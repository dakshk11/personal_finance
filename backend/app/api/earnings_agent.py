import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, EarningsAgentRun, User
from app.schemas.common import (
    EarningsAgentDigestOut,
    EarningsAgentRunOut,
    EarningsAgentRunRequest,
    EarningsAgentRunSummaryOut,
    EarningsAgentSourceOut,
)
from app.services.ai_advisor import AIAdvisorConfigurationError, AIAdvisorProviderError, decrypt_api_key, is_goose_model, is_ollama_model, valid_ai_advisor_model
from app.services.earnings_agent import EarningsAgentLookupError, EarningsAgentSourceError, run_earnings_agent


router = APIRouter(prefix="/earnings-agent", tags=["earnings-agent"])


@router.post("/run", response_model=EarningsAgentRunOut)
def run_digest(
    payload: EarningsAgentRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EarningsAgentRunOut:
    if not valid_ai_advisor_model(payload.model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported model. Use a gpt-* model or ollama:<model_name>.")
    api_key: str | None = None
    if not is_ollama_model(payload.model) and not is_goose_model(payload.model):
        key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before generating an earnings digest.")
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
    try:
        run = run_earnings_agent(db, user.id, payload.query, payload.model, api_key, ollama_base_url=payload.ollama_base_url)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except EarningsAgentLookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EarningsAgentSourceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _run_out(run)


@router.get("/runs", response_model=list[EarningsAgentRunSummaryOut])
def list_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EarningsAgentRunSummaryOut]:
    runs = db.scalars(
        select(EarningsAgentRun)
        .where(EarningsAgentRun.user_id == user.id)
        .order_by(EarningsAgentRun.created_at.desc(), EarningsAgentRun.id.desc())
        .limit(30)
    ).all()
    return [
        EarningsAgentRunSummaryOut(
            id=run.id,
            ticker=run.ticker,
            company_name=run.company_name,
            created_at=run.created_at,
            source_status=run.source_status,
        )
        for run in runs
    ]


@router.get("/runs/{run_id}", response_model=EarningsAgentRunOut)
def get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EarningsAgentRunOut:
    run = db.get(EarningsAgentRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Earnings Agent run not found")
    return _run_out(run)


def _run_out(run: EarningsAgentRun) -> EarningsAgentRunOut:
    source_payloads = [*_source_payloads(run.sec_source_json), *_source_payloads(run.transcript_source_json)]
    digest = _json_load(run.digest_json, {})
    return EarningsAgentRunOut(
        id=run.id,
        query=run.query,
        ticker=run.ticker,
        company_name=run.company_name,
        cik=run.cik,
        model=run.model,
        created_at=run.created_at,
        source_status=run.source_status,
        sources=[
            EarningsAgentSourceOut(**source)
            for source in source_payloads
            if isinstance(source, dict) and source
        ],
        digest=EarningsAgentDigestOut(**digest),
        warnings=_json_load(run.warnings_json, []),
        usage=_json_load(run.usage_json, {}),
    )


def _source_payloads(value: str | None) -> list[dict[str, object]]:
    loaded = _json_load(value, [])
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict) and loaded:
        return [loaded]
    return []


def _json_load(value: str | None, default: object) -> object:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
