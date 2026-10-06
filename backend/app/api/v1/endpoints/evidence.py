from fastapi import APIRouter, File, UploadFile, HTTPException
import shutil
import os
import pdfplumber
from docx import Document

router = APIRouter()

UPLOAD_DIR = "uploaded_evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".csv", ".xlsx", ".xls"}

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
        else:
            text = f"[Text extraction for {extension} not implemented yet]"
    except Exception as e:
        text = f"[Error reading text: {str(e)}]"
    
    return text.strip()

@router.post("/")
async def upload_evidence(file: UploadFile = File(...)):
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Format not allowed: {file_extension}. Allowed formats are: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    try:
        file_location = f"{UPLOAD_DIR}/{file.filename}"
        
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        extracted_text = extract_text(file_location, file_extension)
            
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

    return {
        "info": f"File '{file.filename}' processed successfully.", 
        "path": file_location,
        "extracted_content_preview": extracted_text[:500] + ("..." if len(extracted_text) > 500 else "")
    }