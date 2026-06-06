from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, User
from app.schemas.common import RecommendationAgentRunOut, RecommendationAgentRunRequest
from app.services.ai_advisor import (
    AIAdvisorConfigurationError,
    AIAdvisorProviderError,
    decrypt_api_key,
    is_goose_model,
    is_ollama_model,
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
    if not valid_ai_advisor_model(payload.model) or is_goose_model(payload.model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported model. Use a gpt-* model or ollama:<model_name>.")

    api_key: str | None = None
    if not is_ollama_model(payload.model):
        key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before running Recommendation Agent.")
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)

    try:
        result = run_recommendation_agent(db, user.id, payload, api_key=api_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return RecommendationAgentRunOut(**result)
