from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form, Query
from sqlalchemy.orm import Session
import hashlib
import shutil
import os
import uuid
import pdfplumber
import pandas as pd
from docx import Document

from app.api.v1.dependencies import get_db_session
from app.db.models import EVIDENCE_MAX_BYTES, User
from app.schemas.evidence import EvidenceFileRead
from app.security.auth import get_current_user
from app.api.v1.endpoints.organizations import _active_membership
from app.services.assessments import get_assessment
from app.services.evidence import list_evidence_files, store_evidence_file

router = APIRouter()

UPLOAD_DIR = "uploaded_evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".csv", ".xlsx"}
MAX_FILE_SIZE = EVIDENCE_MAX_BYTES

def extract_text(file_path: str, extension: str) -> str:
    text = ""
    try:
        if extension == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        elif extension == ".pdf":
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        elif extension == ".docx":
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif extension == ".csv":
            df = pd.read_csv(file_path)
            text = df.to_string()
        elif extension == ".xlsx":
            df = pd.read_excel(file_path, engine="openpyxl")
            text = df.to_string()
    except Exception as e:
        raise ValueError(f"Extraction failed: {str(e)}")
    
    if not text.strip():
        raise ValueError("Document contains no readable text.")
        
    return text.strip()

def _remove_file(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def _sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stored:
        for chunk in iter(lambda: stored.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.post("/")
async def upload_evidence(
    organization_id: str = Form(...),
    assessment_id: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    try:
        org_uuid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    membership = _active_membership(db, org_uuid, user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Forbidden: Active membership required.")

    assessment_uuid = None
    if assessment_id:
        try:
            assessment_uuid = uuid.UUID(assessment_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid assessment ID format.")
        if get_assessment(db, org_uuid, assessment_uuid) is None:
            raise HTTPException(status_code=404, detail="Assessment not found.")

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit.")

    original_filename = os.path.basename((file.filename or "").replace("\\", "/")).strip()
    file_extension = os.path.splitext(original_filename)[1].lower()
    
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Format not allowed: {file_extension}.")
    safe_filename = f"{org_uuid}_{uuid.uuid4()}{file_extension}"
    file_location = os.path.join(UPLOAD_DIR, safe_filename)

    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        size_bytes = os.path.getsize(file_location)
        if size_bytes > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds 10MB limit.")

        extracted_text = extract_text(file_location, file_extension)
        record = store_evidence_file(
            db,
            organization_id=org_uuid,
            uploaded_by_user_id=user.id,
            assessment_id=assessment_uuid,
            original_filename=original_filename[:255],
            stored_filename=safe_filename,
            content_type=file.content_type[:255] if file.content_type else None,
            file_extension=file_extension,
            size_bytes=size_bytes,
            sha256=_sha256_of(file_location),
            extracted_text=extracted_text,
        )

    except HTTPException:
        _remove_file(file_location)
        raise
    except ValueError as ve:
        _remove_file(file_location)
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception:
        _remove_file(file_location)
        raise HTTPException(status_code=500, detail="Internal server error.")

    return {
        "info": "File uploaded and parsed successfully.", 
        "id": str(record.id),
        "original_filename": record.original_filename,
        "stored_filename": safe_filename,
        "organization_id": str(org_uuid),
        "assessment_id": str(assessment_uuid) if assessment_uuid else None,
        "size_bytes": size_bytes,
        "sha256": record.sha256,
        "extracted_content_preview": extracted_text[:500]
    }


@router.get("/", response_model=list[EvidenceFileRead])
def read_evidence_files(
    organization_id: uuid.UUID = Query(...),
    assessment_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    if not _active_membership(db, organization_id, user.id):
        raise HTTPException(status_code=403, detail="Forbidden: Active membership required.")
    return list_evidence_files(db, organization_id, assessment_id)