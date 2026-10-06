from fastapi import APIRouter, File, UploadFile, HTTPException
import shutil
import os

router = APIRouter()

UPLOAD_DIR = "uploaded_evidence"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx", ".csv", ".xlsx", ".xls"}

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
            
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")

    return {"info": f"File '{file.filename}' saved successfully.", "path": file_location}