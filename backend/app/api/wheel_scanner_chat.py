import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorNvidiaKey, AIAdvisorOpenAIKey, User
from app.schemas.common import WheelScannerChatOut, WheelScannerChatRequest
from app.services.ai_advisor import (
    AIAdvisorConfigurationError,
    AIAdvisorProviderError,
    decrypt_api_key,
    generate_text,
    is_goose_model,
    is_nvidia_model,
    is_ollama_model,
    response_usage,
    valid_ai_advisor_model,
)


router = APIRouter(prefix="/wheel-scanner", tags=["wheel-scanner"])

WHEEL_SCANNER_SYSTEM_PROMPT = (
    "You are an educational options research assistant for the FinanceOS Wheel Scanner. "
    "Use only the supplied scanner context. Do not place trades, guarantee returns, "
    "or present personalized financial advice. Discuss candidate quality, risks, "
    "technical/volatility signals, and practical due-diligence questions."
)


@router.post("/chat", response_model=WheelScannerChatOut)
def chat(
    payload: WheelScannerChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WheelScannerChatOut:
    if not valid_ai_advisor_model(payload.model) or is_goose_model(payload.model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported model. Use a gpt-* model or ollama:<model_name>.")
    if not payload.context.selected_quotes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select at least one Wheel Scanner row before asking AI chat.")

    api_key: str | None = None
    if is_nvidia_model(payload.model):
        key_row = db.scalar(select(AIAdvisorNvidiaKey).where(AIAdvisorNvidiaKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an NVIDIA API key before using Wheel Scanner AI chat with NVIDIA.")
        api_key = decrypt_api_key(
            key_row.encrypted_api_key,
            get_settings().ai_advisor_key_encryption_secret,
            "NVIDIA API key",
        )
    elif not is_ollama_model(payload.model):
        key_row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
        if not key_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before using Wheel Scanner AI chat.")
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)

    prompt = build_wheel_scanner_chat_prompt(payload)
    try:
        response_text, response_payload = generate_text(
            payload.model,
            prompt,
            api_key=api_key,
            ollama_base_url=payload.ollama_base_url,
            instructions=WHEEL_SCANNER_SYSTEM_PROMPT,
        )
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return WheelScannerChatOut(response_text=response_text, model=payload.model, usage=response_usage(response_payload))


def build_wheel_scanner_chat_prompt(payload: WheelScannerChatRequest) -> str:
    context = payload.context.model_dump(mode="json")
    return "\n".join([
        "Wheel Scanner AI chat request.",
        "",
        "User question:",
        payload.query.strip(),
        "",
        "Scanner context JSON:",
        json.dumps(context, indent=2, sort_keys=True),
        "",
        "Answer format:",
        "- Start with a concise answer to the user's question.",
        "- Compare selected symbols when more than one row is selected.",
        "- Call out CSP, CC, and LEAP suitability only when supported by the supplied fields.",
        "- Highlight major risk flags and what to verify before acting.",
        "- Keep the response educational and avoid order instructions.",
    ])
