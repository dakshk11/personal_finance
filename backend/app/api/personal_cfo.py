from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorOpenAIKey, PersonalCFOFile, PersonalCFOProject, User
from app.schemas.common import (
    PersonalCFODashboardOut,
    PersonalCFOFileOut,
    PersonalCFOFileUpdate,
    PersonalCFOGenerateRequest,
    PersonalCFOMessageIn,
    PersonalCFOProjectCreate,
    PersonalCFOProjectOut,
    PersonalCFORefineRequest,
    PersonalCFOUploadIn,
    PersonalCFOUploadOut,
)
from app.services import personal_cfo as cfo
from app.services.ai_advisor import AIAdvisorConfigurationError, AIAdvisorProviderError, decrypt_api_key, is_goose_model, is_ollama_model


router = APIRouter(prefix="/personal-cfo", tags=["personal-cfo"])


@router.post("/projects", response_model=PersonalCFOProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: PersonalCFOProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOProjectOut:
    return _project_out(cfo.create_project(db, user.id, payload.name))


@router.get("/projects", response_model=list[PersonalCFOProjectOut])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PersonalCFOProjectOut]:
    projects = db.scalars(
        select(PersonalCFOProject)
        .where(PersonalCFOProject.user_id == user.id)
        .order_by(PersonalCFOProject.updated_at.desc(), PersonalCFOProject.id.desc())
    ).all()
    return [_project_out(project, include_detail=False) for project in projects]


@router.get("/projects/{project_id}", response_model=PersonalCFOProjectOut)
def get_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOProjectOut:
    return _project_out(_project_for_user(db, project_id, user))


@router.post("/projects/{project_id}/messages", response_model=PersonalCFOProjectOut)
def submit_message(
    project_id: int,
    payload: PersonalCFOMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOProjectOut:
    project = _project_for_user(db, project_id, user)
    api_key = _openai_api_key(db, user, payload.model)
    try:
        return _project_out(cfo.submit_interview_message(db, project, api_key, payload.model, payload.content, ollama_base_url=payload.ollama_base_url))
    except cfo.PersonalCFOStateError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/projects/{project_id}/one-pager", response_model=PersonalCFOProjectOut)
def generate_one_pager(
    project_id: int,
    payload: PersonalCFOGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOProjectOut:
    project = _project_for_user(db, project_id, user)
    api_key = _openai_api_key(db, user, payload.model)
    try:
        return _project_out(cfo.generate_one_pager(db, project, api_key, payload.model, ollama_base_url=payload.ollama_base_url))
    except cfo.PersonalCFOStateError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/projects/{project_id}/one-pager/refine", response_model=PersonalCFOProjectOut)
def refine_one_pager(
    project_id: int,
    payload: PersonalCFORefineRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOProjectOut:
    project = _project_for_user(db, project_id, user)
    api_key = _openai_api_key(db, user, payload.model)
    try:
        return _project_out(cfo.refine_one_pager(db, project, api_key, payload.model, payload.feedback, ollama_base_url=payload.ollama_base_url))
    except cfo.PersonalCFOStateError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AIAdvisorProviderError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/projects/{project_id}/files", response_model=list[PersonalCFOFileOut])
def list_files(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PersonalCFOFileOut]:
    project = _project_for_user(db, project_id, user)
    return [_file_out(file_row) for file_row in project.files]


@router.get("/projects/{project_id}/files/{file_id}", response_model=PersonalCFOFileOut)
def get_file(
    project_id: int,
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOFileOut:
    project = _project_for_user(db, project_id, user)
    file_row = db.get(PersonalCFOFile, file_id)
    if not file_row or file_row.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personal CFO file not found")
    return _file_out(file_row)


@router.put("/projects/{project_id}/files/{file_id}", response_model=PersonalCFOFileOut)
def update_file(
    project_id: int,
    file_id: int,
    payload: PersonalCFOFileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOFileOut:
    project = _project_for_user(db, project_id, user)
    try:
        return _file_out(cfo.update_file(db, project, file_id, payload.content))
    except cfo.PersonalCFOStateError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/projects/{project_id}/uploads", response_model=PersonalCFOUploadOut, status_code=status.HTTP_201_CREATED)
def upload_financial_file(
    project_id: int,
    payload: PersonalCFOUploadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFOUploadOut:
    project = _project_for_user(db, project_id, user)
    try:
        upload = cfo.create_upload(db, project, payload.file_name, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _upload_out(upload)


@router.get("/projects/{project_id}/dashboard", response_model=PersonalCFODashboardOut)
def dashboard(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PersonalCFODashboardOut:
    project = _project_for_user(db, project_id, user)
    return PersonalCFODashboardOut(**cfo.dashboard_summary(project))


@router.get("/projects/{project_id}/export")
def export_zip(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    project = _project_for_user(db, project_id, user)
    archive = cfo.export_project_zip(db, project)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="Investment Folder.zip"'},
    )


def _project_for_user(db: Session, project_id: int, user: User) -> PersonalCFOProject:
    project = db.get(PersonalCFOProject, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Personal CFO project not found")
    return project


def _openai_api_key(db: Session, user: User, model: str = "") -> str | None:
    if is_ollama_model(model) or is_goose_model(model):
        return None
    row = db.scalar(select(AIAdvisorOpenAIKey).where(AIAdvisorOpenAIKey.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save a validated OpenAI API key in AI Advisor before using Personal CFO.")
    try:
        return decrypt_api_key(row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


def _project_out(project: PersonalCFOProject, *, include_detail: bool = True) -> PersonalCFOProjectOut:
    return PersonalCFOProjectOut(
        id=project.id,
        name=project.name,
        status=project.status,
        current_phase=project.current_phase,
        phase_progress=cfo.load_phase_progress(project),
        phase_complete=cfo.phase_complete(project),
        can_generate_one_pager=cfo.phase_complete(project) and not project.one_pager_generated,
        one_pager_generated=project.one_pager_generated,
        refinement_used=project.refinement_used,
        last_exported_at=project.last_exported_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
        messages=[_message_out(message) for message in project.messages] if include_detail else [],
        files=[_file_out(file_row) for file_row in project.files] if include_detail else [],
        uploads=[_upload_out(upload) for upload in project.uploads] if include_detail else [],
    )


def _message_out(message) -> dict[str, object]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "phase": message.phase,
        "created_at": message.created_at,
    }


def _file_out(file_row: PersonalCFOFile) -> PersonalCFOFileOut:
    return PersonalCFOFileOut(
        id=file_row.id,
        path=file_row.path,
        kind=file_row.kind,
        content=file_row.content,
        created_at=file_row.created_at,
        updated_at=file_row.updated_at,
    )


def _upload_out(upload) -> PersonalCFOUploadOut:
    return PersonalCFOUploadOut(
        id=upload.id,
        file_name=upload.file_name,
        file_type=upload.file_type,
        row_count=cfo.upload_row_count(upload),
        created_at=upload.created_at,
    )
