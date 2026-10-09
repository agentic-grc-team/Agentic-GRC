from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Form
from sqlalchemy.orm import Session
import shutil
import os
import uuid
import pdfplumber
import pandas as pd
from docx import Document

from app.api.v1.dependencies import get_db_session
from app.security.auth import AuthenticatedIdentity, get_authenticated_identity
from app.api.v1.endpoints.organizations import _resolve_user, _active_membership

router = APIRouter()

UPLOAD_DIR = "uploaded_evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".csv", ".xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  

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

@router.post("/")
async def upload_evidence(
    organization_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity)
):
    user = _resolve_user(db, identity, create=False)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized.")
        
    try:
        org_uuid = uuid.UUID(organization_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization ID format.")

    membership = _active_membership(db, org_uuid, user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Forbidden: Active membership required.")

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 10MB limit.")

    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Format not allowed: {file_extension}.")
    safe_filename = f"{organization_id}_{uuid.uuid4()}{file_extension}"
    file_location = os.path.join(UPLOAD_DIR, safe_filename)

    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        extracted_text = extract_text(file_location, file_extension)
            
    except ValueError as ve:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=500, detail="Internal server error.")

    return {
        "info": "File uploaded and parsed successfully.", 
        "original_filename": file.filename,
        "stored_filename": safe_filename,
        "organization_id": organization_id,
        "extracted_content_preview": extracted_text[:500]
    }