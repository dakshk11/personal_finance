from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorLunarCrushKey, AIAdvisorNvidiaKey, AIAdvisorOpenAIKey, AIAdvisorTipRanksKey, User
from app.schemas.common import RecommendationAgentRunOut, RecommendationAgentRunRequest
from app.services.ai_advisor import (
    AIAdvisorConfigurationError,
    AIAdvisorProviderError,
    decrypt_api_key,
    is_goose_model,
    is_nvidia_model,
    is_ollama_model,
    nvidia_model_name,
    NVIDIA_RECOMMENDATION_MODELS,
    valid_ai_advisor_model,
)
from app.services.recommendation_agent import run_recommendation_agent


router = APIRouter(prefix="/ai-advisor/recommendation-agent", tags=["recommendation-agent"])


@router.post("/run", response_model=RecommendationAgentRunOut)
def run(
    payload: RecommendationAgentRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationAgentRunOut:
    if payload.model_mode is None and payload.model == "auto":
        payload = payload.model_copy(update={"model_mode": "foundation"})
    if payload.model_mode is None and (not valid_ai_advisor_model(payload.model) or is_goose_model(payload.model)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported model. Use a gpt-* model or ollama:<model_name>.")

    api_key: str | None = None
    if payload.model_mode == "foundation" or (payload.model_mode is None and not is_ollama_model(payload.model) and not is_nvidia_model(payload.model)):
        key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before running Recommendation Agent.")
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)

    if payload.model_mode == "nvidia" or (payload.model_mode is None and is_nvidia_model(payload.model)):
        model_name = nvidia_model_name(payload.model) if is_nvidia_model(payload.model) else NVIDIA_RECOMMENDATION_MODELS[0]
        if model_name not in NVIDIA_RECOMMENDATION_MODELS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported NVIDIA model.")
        key_row = db.scalar(select(AIAdvisorNvidiaKey).where(AIAdvisorNvidiaKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an NVIDIA API key before running Recommendation Agent with NVIDIA.")
        api_key = decrypt_api_key(
            key_row.encrypted_api_key,
            get_settings().ai_advisor_key_encryption_secret,
            "NVIDIA API key",
        )
        if not is_nvidia_model(payload.model):
            payload = payload.model_copy(update={"model": f"nvidia:{model_name}"})

    if payload.include_tipranks and not (payload.tipranks_api_key or "").strip():
        saved_tipranks_key = db.scalar(select(AIAdvisorTipRanksKey).where(AIAdvisorTipRanksKey.user_id == user.id))
        if saved_tipranks_key:
            payload = payload.model_copy(
                update={
                    "tipranks_api_key": decrypt_api_key(
                        saved_tipranks_key.encrypted_api_key,
                        get_settings().ai_advisor_key_encryption_secret,
                        "TipRanks API key",
                    )
                }
            )

    if payload.include_lunarcrush and not (payload.lunarcrush_api_key or "").strip():
        saved_lunarcrush_key = db.scalar(select(AIAdvisorLunarCrushKey).where(AIAdvisorLunarCrushKey.user_id == user.id))
        if saved_lunarcrush_key:
            payload = payload.model_copy(
                update={
                    "lunarcrush_api_key": decrypt_api_key(
                        saved_lunarcrush_key.encrypted_api_key,
                        get_settings().ai_advisor_key_encryption_secret,
                        "LunarCrush API key",
                    )
                }
            )

    try:
        result = run_recommendation_agent(db, user.id, payload, api_key=api_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return RecommendationAgentRunOut(**result)
