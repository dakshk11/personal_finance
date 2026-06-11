import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, AIAdvisorResearchPromptRun, User
from app.schemas.common import (
    AIAdvisorResearchPromptRunOut,
    AIAdvisorResearchPromptRunRequest,
    AIAdvisorResearchPromptRunSummaryOut,
)
from app.services.ai_advisor import AIAdvisorConfigurationError, AIAdvisorProviderError, decrypt_api_key
from app.services.research_prompts import run_research_prompt


router = APIRouter(prefix="/ai-advisor/research-prompts", tags=["ai-advisor-research-prompts"])


@router.post("/run", response_model=AIAdvisorResearchPromptRunOut)
def run_prompt(
    payload: AIAdvisorResearchPromptRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorResearchPromptRunOut:
    openai_api_key: str | None = None
    try:
        if payload.provider == "openai_web":
            key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
            if not key_row:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before running OpenAI Web Search.")
            openai_api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)

        run = run_research_prompt(
            db,
            user_id=user.id,
            template_id=payload.template_id,
            provider=payload.provider,
            model=payload.model,
            inputs=payload.inputs,
            openai_api_key=openai_api_key,
            ollama_base_url=payload.ollama_base_url,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY if detail.startswith("Missing required inputs") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _run_out(run)


@router.get("/runs", response_model=list[AIAdvisorResearchPromptRunSummaryOut])
def list_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIAdvisorResearchPromptRunSummaryOut]:
    rows = db.scalars(
        select(AIAdvisorResearchPromptRun)
        .where(AIAdvisorResearchPromptRun.user_id == user.id)
        .order_by(AIAdvisorResearchPromptRun.created_at.desc(), AIAdvisorResearchPromptRun.id.desc())
        .limit(50)
    ).all()
    return [
        AIAdvisorResearchPromptRunSummaryOut(
            id=row.id,
            template_id=row.template_id,
            template_title=row.template_title,
            provider=row.provider,
            model=row.model,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/runs/{run_id}", response_model=AIAdvisorResearchPromptRunOut)
def get_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorResearchPromptRunOut:
    run = db.get(AIAdvisorResearchPromptRun, run_id)
    if not run or run.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research prompt run not found")
    return _run_out(run)


def _run_out(run: AIAdvisorResearchPromptRun) -> AIAdvisorResearchPromptRunOut:
    return AIAdvisorResearchPromptRunOut(
        id=run.id,
        template_id=run.template_id,
        template_title=run.template_title,
        provider=run.provider,
        model=run.model,
        inputs=json.loads(run.input_json or "{}"),
        prompt_text=run.prompt_text,
        response_text=run.response_text,
        sources=json.loads(run.sources_json or "[]"),
        usage=json.loads(run.usage_json or "{}"),
        warnings=json.loads(run.warnings_json or "[]"),
        created_at=run.created_at,
    )
