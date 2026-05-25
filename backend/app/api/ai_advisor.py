import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, AIAdvisorReport, User
from app.schemas.common import (
    AIAdvisorOpenAIKeyIn,
    AIAdvisorOpenAIKeyOut,
    AIAdvisorReportOut,
    AIAdvisorReportSummaryOut,
    AIAdvisorRetirementRunRequest,
)
from app.services.ai_advisor import (
    AIAdvisorConfigurationError,
    AIAdvisorProviderError,
    api_key_fingerprint,
    build_retirement_prompt,
    create_openai_response,
    decrypt_api_key,
    encrypt_api_key,
    get_retirement_prompt_module,
    missing_required_fields,
    now_utc_naive,
    response_usage,
    sanitized_inputs,
    valid_ai_advisor_model,
    validate_openai_api_key_format,
)


router = APIRouter(prefix="/ai-advisor", tags=["ai-advisor"])


@router.get("/openai-key", response_model=AIAdvisorOpenAIKeyOut)
def get_openai_key_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorOpenAIKeyOut:
    row = _openai_key_row(db, user)
    if not row:
        return AIAdvisorOpenAIKeyOut(has_key=False)
    return AIAdvisorOpenAIKeyOut(
        has_key=True,
        key_fingerprint=row.key_fingerprint,
        validated_at=row.validated_at,
        updated_at=row.updated_at,
    )


@router.put("/openai-key", response_model=AIAdvisorOpenAIKeyOut)
def save_openai_key(
    payload: AIAdvisorOpenAIKeyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorOpenAIKeyOut:
    api_key = payload.api_key.strip()
    try:
        validate_openai_api_key_format(api_key)
        encrypted = encrypt_api_key(api_key, get_settings().ai_advisor_key_encryption_secret)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        detail = "OpenAI API key could not be saved."
        provider_message = str(exc).strip()
        if provider_message and provider_message != "OpenAI request failed.":
            detail = provider_message
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    timestamp = now_utc_naive()
    row = _openai_key_row(db, user)
    if row:
        row.encrypted_api_key = encrypted
        row.key_fingerprint = api_key_fingerprint(api_key)
        row.validated_at = timestamp
        row.updated_at = timestamp
    else:
        row = AIAdvisorOpenAIKey(
            user_id=user.id,
            encrypted_api_key=encrypted,
            key_fingerprint=api_key_fingerprint(api_key),
            validated_at=timestamp,
            updated_at=timestamp,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return AIAdvisorOpenAIKeyOut(
        has_key=True,
        key_fingerprint=row.key_fingerprint,
        validated_at=row.validated_at,
        updated_at=row.updated_at,
    )


@router.delete("/openai-key", response_model=AIAdvisorOpenAIKeyOut)
def delete_openai_key(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorOpenAIKeyOut:
    row = _openai_key_row(db, user)
    if row:
        db.delete(row)
        db.commit()
    return AIAdvisorOpenAIKeyOut(has_key=False)


@router.post("/retirement-plan/run", response_model=AIAdvisorReportOut)
def run_retirement_plan(
    payload: AIAdvisorRetirementRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorReportOut:
    module = get_retirement_prompt_module(payload.module_id)
    if not module:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown retirement plan module.")
    if not valid_ai_advisor_model(payload.model):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OpenAI model.")
    missing = missing_required_fields(module, payload.inputs)
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required inputs: {', '.join(missing)}")

    key_row = _openai_key_row(db, user)
    if not key_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an OpenAI API key before generating a report.")

    inputs = sanitized_inputs(module, payload.inputs)
    prompt_text = build_retirement_prompt(module, inputs)
    try:
        api_key = decrypt_api_key(key_row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
        response_text, response_payload = create_openai_response(api_key, payload.model, prompt_text)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    report = AIAdvisorReport(
        user_id=user.id,
        module_id=module.id,
        module_title=module.title,
        model=payload.model,
        input_snapshot_json=json.dumps(inputs, separators=(",", ":"), sort_keys=True),
        prompt_text=prompt_text,
        response_text=response_text,
        usage_json=json.dumps(response_usage(response_payload), separators=(",", ":"), sort_keys=True),
        error_json=None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _report_out(report)


@router.get("/reports", response_model=list[AIAdvisorReportSummaryOut])
def list_reports(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AIAdvisorReportSummaryOut]:
    reports = db.scalars(
        select(AIAdvisorReport)
        .where(AIAdvisorReport.user_id == user.id)
        .order_by(AIAdvisorReport.created_at.desc(), AIAdvisorReport.id.desc())
    ).all()
    return [
        AIAdvisorReportSummaryOut(
            id=report.id,
            module_id=report.module_id,
            module_title=report.module_title,
            model=report.model,
            created_at=report.created_at,
        )
        for report in reports
    ]


@router.get("/reports/{report_id}", response_model=AIAdvisorReportOut)
def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AIAdvisorReportOut:
    report = db.get(AIAdvisorReport, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI advisor report not found")
    return _report_out(report)


def _openai_key_row(db: Session, user: User) -> AIAdvisorOpenAIKey | None:
    return db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))


def _report_out(report: AIAdvisorReport) -> AIAdvisorReportOut:
    return AIAdvisorReportOut(
        id=report.id,
        module_id=report.module_id,
        module_title=report.module_title,
        model=report.model,
        input_snapshot=json.loads(report.input_snapshot_json or "{}"),
        prompt_text=report.prompt_text,
        response_text=report.response_text,
        usage=json.loads(report.usage_json or "{}"),
        error=json.loads(report.error_json) if report.error_json else None,
        created_at=report.created_at,
    )
